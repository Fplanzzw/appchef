/**
 * RAG 设置面板 - 右下角悬浮按钮
 */
import {useState, useRef, useEffect} from "react";
import {Settings, X, Upload, FileText, Search, ChevronRight, ChevronDown} from "lucide-react";
import {uploadRAGDocument, searchRAG, getRAGStatus} from "@/lib/api";

interface RAGPanelProps {
    onClose: () => void;
}

export function RAGPanel({onClose}: RAGPanelProps) {
    const [open, setOpen] = useState(false);
    const [file, setFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [status, setStatus] = useState<{ indexed: number; lastUpdated?: string }>({ indexed: 0 });
    const [searchQuery, setSearchQuery] = useState("");
    const [searchResults, setSearchResults] = useState<any[]>([]);
    const [searchDetails, setSearchDetails] = useState<any>(null);
    const [expandedDetails, setExpandedDetails] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // 获取 RAG 状态
    const fetchStatus = async () => {
        try {
            const data = await getRAGStatus();
            setStatus(data);
        } catch (error) {
            console.error("获取 RAG 状态失败:", error);
        }
    };

    // 上传文档
    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selected = e.target.files?.[0];
        if (selected) {
            setFile(selected);
        }
    };

    const handleUpload = async () => {
        if (!file) return;
        
        setUploading(true);
        try {
            const result = await uploadRAGDocument(file);
            if (result.success) {
                await fetchStatus();
                setFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
            }
        } catch (error) {
            console.error("上传失败:", error);
        } finally {
            setUploading(false);
        }
    };

    // 搜索 RAG
    const handleSearch = async () => {
        if (!searchQuery.trim()) return;
        
        try {
            const data = await searchRAG(searchQuery);
            setSearchResults(data.results);
            setSearchDetails(data.details);
            setExpandedDetails(false);
        } catch (error) {
            console.error("搜索失败:", error);
        }
    };

    // 初始化加载状态
    useEffect(() => {
        fetchStatus();
    }, []);

    return (
        <div className="fixed bottom-4 right-4 z-[200]">
            {/* 悬浮按钮 */}
            <button
                onClick={() => setOpen(!open)}
                className="bg-gradient-to-br from-blue-500 to-indigo-500 text-white rounded-full p-3 shadow-lg hover:shadow-xl transition-all"
            >
                <Settings size={20} className="text-white"/>
            </button>

            {/* 面板 */}
            {open && (
                <div className="absolute bottom-16 right-0 w-80 bg-white rounded-xl shadow-2xl border border-gray-200 overflow-hidden">
                    <div className="p-4 border-b border-gray-100">
                        <div className="flex items-center justify-between">
                            <h3 className="font-semibold text-gray-800">RAG 知识库</h3>
                            <button
                                onClick={onClose}
                                className="p-1 hover:bg-gray-100 rounded-lg transition-colors"
                            >
                                <X size={18} className="text-gray-400"/>
                            </button>
                        </div>
                    </div>

                    <div className="p-4 space-y-4">
                        {/* 状态信息 */}
                        <div className="bg-blue-50 rounded-lg p-3">
                            <div className="flex items-center gap-2 text-sm text-blue-700">
                                <FileText size={16}/>
                                <span>已索引: {status.indexed} 个文档</span>
                            </div>
                            {status.lastUpdated && (
                                <div className="text-xs text-blue-600 mt-1">
                                    最后更新: {status.lastUpdated}
                                </div>
                            )}
                        </div>

                        {/* 文档上传 */}
                        <div>
                            <h4 className="font-medium text-gray-700 mb-2">上传资料</h4>
                            <div className="space-y-2">
                                <input
                                    ref={fileInputRef}
                                    type="file"
                                    accept=".pdf,.doc,.docx,.txt"
                                    onChange={handleFileChange}
                                    className="hidden"
                                />
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    className="w-full px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-100 transition-colors flex items-center justify-center gap-2"
                                >
                                    <Upload size={16}/>
                                    选择文件
                                </button>
                                {file && (
                                    <div className="text-sm text-gray-600 bg-gray-50 rounded px-2 py-1">
                                        {file.name}
                                    </div>
                                )}
                                {uploading && (
                                    <div className="text-sm text-blue-600">上传中...</div>
                                )}
                                <button
                                    onClick={handleUpload}
                                    disabled={!file || uploading}
                                    className="w-full px-3 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                    {uploading ? "上传中..." : "上传文档"}
                                </button>
                            </div>
                        </div>

                        {/* 搜索功能 */}
                        <div>
                            <h4 className="font-medium text-gray-700 mb-2">知识搜索</h4>
                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    placeholder="输入问题..."
                                    className="flex-1 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                                />
                                <button
                                    onClick={handleSearch}
                                    className="px-3 py-2 bg-blue-500 text-white rounded-lg text-sm hover:bg-blue-600 transition-colors"
                                >
                                    <Search size={16}/>
                                </button>
                            </div>
                        </div>

                        {/* 搜索结果 */}
                        {searchResults.length > 0 && (
                            <div>
                                <h4 className="font-medium text-gray-700 mb-2">搜索结果</h4>
                                <div className="space-y-2 max-h-48 overflow-y-auto">
                                    {searchResults.map((result, idx) => (
                                        <div key={idx} className="bg-gray-50 rounded-lg p-3">
                                            <div className="text-sm font-medium text-gray-800">{result.title}</div>
                                            <div className="text-xs text-gray-600 mt-1 line-clamp-2">{result.content}</div>
                                            <div className="text-xs text-blue-600 mt-1">相关性: {result.score}</div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* 搜索详情（可展开） */}
                        {searchDetails && (
                            <div>
                                <button
                                    onClick={() => setExpandedDetails(!expandedDetails)}
                                    className="w-full flex items-center justify-between px-3 py-2 bg-gray-50 rounded-lg text-sm text-gray-700 hover:bg-gray-100 transition-colors"
                                >
                                    <span>查看过程详情</span>
                                    {expandedDetails ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                                </button>
                                {expandedDetails && (
                                    <div className="mt-2 p-3 bg-gray-50 rounded-lg text-xs text-gray-600 space-y-2">
                                        <div><strong>检索:</strong> {searchDetails.retrieval}</div>
                                        <div><strong>评分:</strong> {searchDetails.scoring}</div>
                                        <div><strong>重写:</strong> {searchDetails.rewriting}</div>
                                        <div><strong>来源:</strong> {searchDetails.sources}</div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}