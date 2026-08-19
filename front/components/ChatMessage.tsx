/**
 * 聊天消息组件 — 蓝色配色，支持菜谱拒绝按钮
 */
import {useState} from "react";
import {Message} from "@/types/chat";
import {User, Bot, Loader2, ChefHat, ThumbsDown} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ChatMessageProps {
    message: Message;
    onReject?: (recipeName: string) => void;
}

/**
 * 从助手回复中尝试提取第一个菜名（## 标题 或 **粗体** 后的第一个短语）
 */
function extractFirstRecipeName(content: string): string | null {
    const headingMatch = content.match(/^#{1,3}\s+(.+)$/m);
    if (headingMatch) return headingMatch[1].replace(/[*]/g, "").trim();
    const boldMatch = content.match(/\*\*(.+?)\*\*/);
    if (boldMatch) return boldMatch[1].trim();
    return null;
}

export function ChatMessage({message, onReject}: ChatMessageProps) {
    const isUser = message.role === "user";
    const [showReject, setShowReject] = useState(false);
    const recipeName = !isUser && message.content ? extractFirstRecipeName(message.content) : null;

    return (
        <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
            <div
                className={`flex gap-3 max-w-[85%] ${isUser ? "flex-row-reverse" : ""} animate-fade-in`}
            >
                {/* 头像 */}
                <div
                    className={`flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center shadow-md ${
                        isUser
                            ? "bg-gradient-to-br from-blue-400 to-blue-600"
                            : "bg-gradient-to-br from-blue-400 to-indigo-500"
                    }`}
                >
                    {message.loading || message.streaming ? (
                        <Loader2 size={16} className="text-white animate-spin"/>
                    ) : isUser ? (
                        <User size={16} className="text-white"/>
                    ) : (
                        <ChefHat size={16} className="text-white"/>
                    )}
                </div>

                {/* 消息内容 */}
                <div className="relative group">
                    <div
                        className={`rounded-2xl px-4 py-3 shadow-sm ${
                            isUser
                                ? "bg-gradient-to-br from-blue-500 to-blue-600 text-white"
                                : "bg-white/90 text-gray-800 border border-gray-100"
                        }`}
                    >
                        {message.imageUrl && (
                            <img
                                src={message.imageUrl}
                                alt="上传的图片"
                                className="rounded-lg mb-2 max-w-48 object-cover"
                            />
                        )}
                        {isUser ? (
                            <p className="whitespace-pre-wrap leading-relaxed">
                                {typeof message.content === 'string' ? message.content : JSON.stringify(message.content)}
                            </p>
                        ) : (
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={{
                                    h1: ({children}) => <h1 className="text-xl font-bold mb-2 mt-3">{children}</h1>,
                                    h2: ({children}) => <h2 className="text-lg font-bold mb-2 mt-3">{children}</h2>,
                                    h3: ({children}) => <h3 className="text-base font-semibold mb-1 mt-2">{children}</h3>,
                                    p: ({children}) => <p className="mb-2 last:mb-0">{children}</p>,
                                    ul: ({children}) => <ul className="list-disc ml-4 mb-2 space-y-1">{children}</ul>,
                                    ol: ({children}) => <ol className="list-decimal ml-4 mb-2 space-y-1">{children}</ol>,
                                    li: ({children}) => <li className="mb-1 leading-relaxed">{children}</li>,
                                    a: ({href, children}) => <a href={href} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">{children}</a>,
                                    strong: ({children}) => <strong className="font-semibold">{children}</strong>,
                                    em: ({children}) => <em className="italic">{children}</em>,
                                    code: ({children}) => <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono">{children}</code>,
                                    pre: ({children}) => <pre className="bg-gray-100 p-3 rounded-lg overflow-x-auto mb-2">{children}</pre>,
                                    blockquote: ({children}) => <blockquote className="border-l-4 border-blue-300 pl-3 italic text-gray-600 mb-2">{children}</blockquote>,
                                    table: ({children}) => <table className="w-full border-collapse border border-gray-300 mb-3">{children}</table>,
                                    thead: ({children}) => <thead className="bg-gray-50">{children}</thead>,
                                    tbody: ({children}) => <tbody>{children}</tbody>,
                                    tr: ({children}) => <tr className="border-b border-gray-200">{children}</tr>,
                                    th: ({children}) => <th className="border border-gray-300 px-3 py-2 text-left font-semibold bg-gray-50">{children}</th>,
                                    td: ({children}) => <td className="border border-gray-300 px-3 py-2">{children}</td>,
                                }}
                            >
                                {String(message.content || "")}
                            </ReactMarkdown>
                        )}
                    </div>

                    {/* 拒绝按钮 - 仅助手消息且非流式中 */}
                    {!isUser && !message.streaming && recipeName && onReject && (
                        <button
                            onClick={() => onReject(recipeName)}
                            onMouseEnter={() => setShowReject(true)}
                            onMouseLeave={() => setShowReject(false)}
                            className="absolute -bottom-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity px-2 py-1 bg-white border border-gray-200 rounded-lg shadow-sm hover:bg-blue-50 hover:border-blue-200 text-xs text-gray-500 hover:text-blue-600 flex items-center gap-1"
                        >
                            <ThumbsDown size={12}/>
                            不喜欢
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
