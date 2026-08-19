"""RAG API"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from typing import List, Dict, Any

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from appchef.services.rag_parser import parse_document, split_text_into_chunks
from appchef.services.vector_store import get_vector_store
from appchef.services.rag_summarizer import summarize_question
from appchef.memory.store import get_memory_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["RAG"])


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    vector_weight: float = 0.7
    bm25_weight: float = 0.3


class RAGSearchResponse(BaseModel):
    answer: str
    chunks: List[dict]
    retrieval_time: float


class RAGProcessLogRequest(BaseModel):
    query: str
    top_k: int = 10  # 获取更多日志用于分析


class RAGProcessLogResponse(BaseModel):
    logs: List[Dict[str, Any]]
    total_count: int


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), user_id: str = "default"):
    """上传文档（PDF/DOC/DOCX/TXT）并解析为向量存储。

    Args:
        file: 上传的文件
        user_id: 用户ID（默认 default）

    Returns:
        上传结果，包含文档ID和分块数量
    """
    # 检查文件类型
    filename = file.filename or ""
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if file_ext not in ["pdf", "doc", "docx", "txt", "word"]:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file_ext}。仅支持 PDF、DOC、DOCX、TXT、WORD")

    # 保存到临时文件
    temp_file = None
    try:
        # 创建临时文件
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}")
        content = await file.read()
        temp_file.write(content)
        temp_file.close()
        temp_path = temp_file.name

        logger.info(f"已保存临时文件: {temp_path}，大小: {len(content)} bytes")

        # 解析文档
        text = parse_document(temp_path, file_ext)
        if not text:
            raise HTTPException(status_code=400, detail="文档解析失败或内容为空")

        logger.info(f"解析文档成功，文本长度: {len(text)} 字符")

        # 分块
        chunks = split_text_into_chunks(text, chunk_size=500, overlap=50)
        logger.info(f"分块完成，共 {len(chunks)} 块")

        # 存储到向量库
        vector_store = get_vector_store()
        doc_id = vector_store.add_document(
            user_id=user_id,
            filename=filename,
            file_type=file_ext,
            chunks=chunks,
        )

        return {
            "success": True,
            "message": "文档上传成功",
            "document_id": doc_id,
            "filename": filename,
            "file_type": file_ext,
            "chunk_count": len(chunks),
        }
    except Exception as e:
        logger.error(f"上传文档失败: {e}")
        raise HTTPException(status_code=500, detail=f"上传文档失败: {str(e)}")
    finally:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
                logger.info(f"已删除临时文件: {temp_file.name}")
            except Exception as e:
                logger.warning(f"删除临时文件失败: {e}")


@router.post("/search", response_model=RAGSearchResponse)
async def search_rag(request: RAGSearchRequest, user_id: str = "default") -> RAGSearchResponse:
    """RAG 检索 + 总结。

    Args:
        request: RAGSearchRequest
        user_id: 用户ID（默认 default）

    Returns:
        检索结果和总结
    """
    start_time = time.time()

    try:
        # 检索
        vector_store = get_vector_store()
        chunks = vector_store.search(
            user_id=user_id,
            query=request.query,
            top_k=request.top_k,
            vector_weight=request.vector_weight,
            bm25_weight=request.bm25_weight,
        )

        if not chunks:
            return RAGSearchResponse(
                answer="未找到相关文档，请先上传知识文档。",
                chunks=[],
                retrieval_time=time.time() - start_time,
            )

        # 提取chunk文本用于总结
        chunk_texts = [chunk["chunk_text"] for chunk in chunks]

        # 总结
        answer = summarize_question(request.query, chunk_texts)

        # 构造返回的chunks信息
        chunk_infos = []
        for chunk in chunks:
            chunk_infos.append({
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "doc_info": chunk["doc_info"],
                "vector_score": chunk["vector_score"],
                "bm25_score": chunk["bm25_score"],
                "final_score": chunk["final_score"],
                "chunk_preview": chunk["chunk_text"][:200] + "..." if len(chunk["chunk_text"]) > 200 else chunk["chunk_text"],
            })

        retrieval_time = time.time() - start_time

        return RAGSearchResponse(
            answer=answer,
            chunks=chunk_infos,
            retrieval_time=retrieval_time,
        )
    except Exception as e:
        logger.error(f"RAG检索失败: {e}")
        raise HTTPException(status_code=500, detail=f"RAG检索失败: {str(e)}")


@router.get("/status")
async def get_rag_status(user_id: str = "default"):
    """获取RAG状态信息。

    Args:
        user_id: 用户ID（默认 default）

    Returns:
        状态信息，包含文档数、分块数、最近上传文档
    """
    try:
        vector_store = get_vector_store()
        status = vector_store.get_status(user_id=user_id)
        return status
    except Exception as e:
        logger.error(f"获取RAG状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取RAG状态失败: {str(e)}")


@router.delete("/document/{doc_id}")
async def delete_rag_document(doc_id: int):
    """删除RAG文档。

    Args:
        doc_id: 文档ID

    Returns:
        删除结果
    """
    try:
        vector_store = get_vector_store()
        success = vector_store.delete_document(doc_id=doc_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"文档 ID={doc_id} 不存在")
        return {"success": True, "message": f"已删除文档 ID={doc_id}"}
    except Exception as e:
        logger.error(f"删除RAG文档失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除RAG文档失败: {str(e)}")


@router.post("/process-logs", response_model=RAGProcessLogResponse)
async def get_rag_process_logs(request: RAGProcessLogRequest, user_id: str = "default"):
    """获取RAG过程日志。

    Args:
        request: RAGProcessLogRequest
        user_id: 用户ID（默认 default）

    Returns:
        RAG过程日志列表
    """
    try:
        mem = get_memory_store()
        logs = mem._conn.execute(
            """
            SELECT id, user_id, query, document_id, chunk_id, step_type, details, created_at
            FROM rag_process_logs
            WHERE user_id = ? AND query = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, request.query, request.top_k),
        ).fetchall()

        log_list = []
        for row in logs:
            log_list.append({
                "id": row["id"],
                "user_id": row["user_id"],
                "query": row["query"],
                "document_id": row["document_id"],
                "chunk_id": row["chunk_id"],
                "step_type": row["step_type"],
                "details": json.loads(row["details"]),
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["created_at"])),
            })

        return RAGProcessLogResponse(
            logs=log_list,
            total_count=len(log_list)
        )
    except Exception as e:
        logger.error(f"获取RAG过程日志失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取RAG过程日志失败: {str(e)}")