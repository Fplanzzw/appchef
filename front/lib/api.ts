/**
 * API 调用封装
 */
const API_BASE = "http://localhost:8001";

/**
 * 获取 OSS 预签名上传 URL
 */
export async function getOssPresignUrl(filename: string): Promise<{ uploadUrl: string; accessUrl: string; contentType: string }> {
    const response = await fetch(`${API_BASE}/api/v1/oss/presign?filename=${filename}`);
    if (!response.ok) {
        throw new Error("获取上传 URL 失败");
    }
    const data = await response.json();
    return {
        uploadUrl: data.uploadUrl.trim().replace(/^["']|["']$/g, ''),
        accessUrl: data.accessUrl.trim().replace(/^["']|["']$/g, ''),
        contentType: data.contentType
    };
}

/**
 * 上传图片到 OSS
 */
export async function uploadImageToOss(file: File): Promise<string> {
    const ext = file.name.split(".").pop() || "jpg";
    const filename = `${Date.now()}.${ext}`;
    const { uploadUrl, accessUrl, contentType } = await getOssPresignUrl(filename);

    const response = await fetch(uploadUrl, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": contentType },
    });

    if (!response.ok) {
        throw new Error(`图片上传失败: ${response.status}`);
    }
    return accessUrl;
}

/**
 * 流式聊天
 */
export async function streamChat(
    message: string,
    onChunk: (chunk: string) => void,
    image_url?: string,
    onError?: (error: Error) => void,
    onComplete?: () => void,
    threadId?: string,
    userId?: string,
    lon?: number,
    lat?: number,
    abortController?: AbortController,
): Promise<void> {
    try {
        const url = new URL(`${API_BASE}/api/v1/chat/stream`);

        const response = await fetch(url.toString(), {
            method: "POST",
            body: JSON.stringify({
                message,
                image_url: image_url || null,
                thread_id: threadId,
                user_id: userId || "default",
                lon: lon ?? null,
                lat: lat ?? null,
            }),
            headers: { "Content-Type": "application/json" },
            signal: abortController?.signal,
        });

        if (!response.ok) {
            throw new Error(`请求失败: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
            throw new Error("无法读取响应流");
        }

        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                onComplete?.();
                break;
            }
            const chunk = decoder.decode(value, { stream: true });
            onChunk(chunk);
        }
    } catch (error) {
        if (!(error instanceof Error) || error.name !== 'AbortError') {
            onError?.(error as Error);
        }
    }
}

/**
 * 获取聊天历史
 */
export async function getChatHistory(threadId: string): Promise<{ role: string; content: string }[]> {
    const response = await fetch(`${API_BASE}/api/v1/chat/messages?thread_id=${threadId}`);
    if (!response.ok) {
        throw new Error("获取历史消息失败");
    }
    const data = await response.json();
    return data.messages;
}

/**
 * 清空聊天历史
 */
export async function clearChatHistory(threadId: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/v1/chat/messages?thread_id=${threadId}`, {
        method: "DELETE",
    });
    if (!response.ok) {
        throw new Error("清空历史消息失败");
    }
}

/**
 * 食谱反馈（拒绝/补充说明）
 */
export async function sendRecipeFeedback(
    threadId: string,
    action: "reject" | "clarify",
    options?: {
        userId?: string;
        recipeName?: string;
        recentRecipes?: string[];
        userClarification?: string;
    }
): Promise<{
    ok: boolean;
    phase?: string;
    question?: string;
    reject_count?: number;
    recent_recipes?: string[];
    long_term_saved?: { kind: string; content: string }[];
    instruction?: string;
}> {
    const response = await fetch(`${API_BASE}/api/v1/chat/feedback`, {
        method: "POST",
        body: JSON.stringify({
            thread_id: threadId,
            user_id: options?.userId || "default",
            action,
            recipe_name: options?.recipeName,
            recent_recipes: options?.recentRecipes,
            user_clarification: options?.userClarification,
        }),
        headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) {
        throw new Error("反馈请求失败");
    }
    return response.json();
}

/**
 * 获取浏览器定位
 */
export function getBrowserLocation(): Promise<{ lon: number; lat: number } | null> {
    return new Promise((resolve) => {
        if (!navigator.geolocation) {
            resolve(null);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (pos) => resolve({ lon: pos.coords.longitude, lat: pos.coords.latitude }),
            () => resolve(null),
            { timeout: 5000 }
        );
    });
}

/**
 * RAG 文档上传
 */
export async function uploadRAGDocument(file: File): Promise<{ success: boolean; message?: string }> {
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await fetch(`${API_BASE}/api/v1/rag/upload`, {
            method: "POST",
            body: formData,
        });
        return await response.json();
    } catch (error) {
        return { success: false, message: "上传失败" };
    }
}

/**
 * RAG 搜索
 */
export async function searchRAG(query: string): Promise<{ results: any[]; details: any }> {
    const response = await fetch(`${API_BASE}/api/v1/rag/search`, {
        method: "POST",
        body: JSON.stringify({ query }),
        headers: { "Content-Type": "application/json" },
    });
    return await response.json();
}

/**
 * 获取 RAG 状态
 */
export async function getRAGStatus(): Promise<{ indexed: number; lastUpdated?: string }> {
    const response = await fetch(`${API_BASE}/api/v1/rag/status`);
    return await response.json();
}