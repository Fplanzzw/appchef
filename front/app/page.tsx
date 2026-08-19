"use client";

import {useState, useEffect, useRef} from "react";
import {Message} from "@/types/chat";
import {ChatMessage} from "@/components/ChatMessage";
import {ChatInput} from "@/components/ChatInput";
import {FeedbackDialog} from "@/components/FeedbackDialog";
import {FestivalReminder} from "@/components/FestivalReminder";
import {RAGPanel} from "@/components/RAGPanel";
import {ReminderSettingsPanel} from "@/components/ReminderSettingsPanel";
import {uploadImageToOss, streamChat, getChatHistory, clearChatHistory, getBrowserLocation, uploadRAGDocument, searchRAG, getRAGStatus, getReminders, dismissReminder, updateReminderSetting} from "@/lib/api";
import {generateUUID} from "@/lib/utils";
import {UtensilsCrossed, ChefHat, Plus, MapPin, Settings, X} from "lucide-react";

export default function Home() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [processing, setProcessing] = useState(false);
    const [threadId, setThreadId] = useState<string>("");
    const [location, setLocation] = useState<{lon: number; lat: number} | null>(null);
    const [locationLoading, setLocationLoading] = useState(false);
    const [feedbackOpen, setFeedbackOpen] = useState(false);
    const [feedbackRecipe, setFeedbackRecipe] = useState("");
    const [ragOpen, setRagOpen] = useState(false);
    const [reminderSettingsOpen, setReminderSettingsOpen] = useState(false);
    const [abortController, setAbortController] = useState<AbortController | null>(null);
    const [reminders, setReminders] = useState<any[]>([]);
    const [reminderSettings, setReminderSettings] = useState<Record<string, boolean>>({});
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const messageIdCounter = useRef(0);

    // 加载历史消息
    const loadHistory = async (id: string) => {
        try {
            const history = await getChatHistory(id);
            if (history && history.length > 0) {
                const loadedMessages: Message[] = history.map((msg, index) => {
                    let content = "";
                    let imageUrl: string | undefined;

                    if (typeof msg.content === 'string') {
                        content = msg.content;
                    } else if (Array.isArray(msg.content)) {
                        const parts = msg.content as { type: string; text?: string; url?: string }[];
                        for (const part of parts) {
                            if (part.type === 'text' && part.text) {
                                content += part.text;
                            } else if (part.type === 'image' && part.url) {
                                imageUrl = part.url;
                            }
                        }
                    }

                    return {
                        id: `history_${index}_${Date.now()}`,
                        role: msg.role as "user" | "assistant",
                        content,
                        imageUrl,
                        timestamp: Date.now() - (history.length - index) * 1000,
                    };
                });
                setMessages(loadedMessages);
                messageIdCounter.current = loadedMessages.length;
            }
        } catch (error) {
            console.error("加载历史消息失败:", error);
        }
    };

    // 加载提醒设置
    const loadReminderSettings = async () => {
        try {
            const settings = await getReminders("default");
            const settingsMap: Record<string, boolean> = {};
            settings.forEach((reminder: any) => {
                const key = `${reminder.reminder_type}_${reminder.festival_name || reminder.season}`;
                settingsMap[key] = reminder.dismissed === 0;
            });
            setReminderSettings(settingsMap);
        } catch (error) {
            console.error("加载提醒设置失败:", error);
        }
    };

    // 加载提醒列表
    const loadReminders = async () => {
        try {
            const activeReminders = await getReminders("default");
            setReminders(activeReminders);
        } catch (error) {
            console.error("加载提醒列表失败:", error);
        }
    };

    // 页面加载时
    useEffect(() => {
        let storedThreadId = localStorage.getItem("thread_id");
        if (!storedThreadId) {
            storedThreadId = generateUUID();
            localStorage.setItem("thread_id", storedThreadId);
        }
        setThreadId(storedThreadId);
        loadHistory(storedThreadId);
        loadReminderSettings();
        loadReminders();
    }, []);

    // 获取定位
    const handleGetLocation = async () => {
        setLocationLoading(true);
        try {
            const loc = await getBrowserLocation();
            if (loc) {
                setLocation(loc);
            } else {
                console.warn("无法获取定位");
            }
        } finally {
            setLocationLoading(false);
        }
    };

    // 新建会话
    const handleNewChat = async () => {
        if (threadId) {
            try {
                await clearChatHistory(threadId);
            } catch (error) {
                console.error("清空历史失败:", error);
            }
        }
        const newThreadId = generateUUID();
        localStorage.setItem("thread_id", newThreadId);
        setThreadId(newThreadId);
        setMessages([]);
        messageIdCounter.current = 0;
    };

    // 滚动到底部
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({behavior: "smooth"});
    }, [messages]);

    // 添加消息
    const addMessage = (message: Omit<Message, "id" | "timestamp">) => {
        messageIdCounter.current += 1;
        const newMessage: Message = {
            ...message,
            id: `msg_${messageIdCounter.current}_${Date.now()}`,
            timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, newMessage]);
        return newMessage;
    };

    // 处理发送消息
    const handleSend = async (text: string, file?: File) => {
        if (processing) return;

        let imageUrl: string | undefined;

        if (file) {
            try {
                imageUrl = await uploadImageToOss(file);
            } catch (error) {
                console.error("图片上传失败:", error);
                addMessage({
                    role: "assistant",
                    content: "图片上传失败，请稍后重试。",
                });
                return;
            }
        }

        addMessage({
            role: "user",
            content: text || "上传了一张食材图片",
            imageUrl,
        });

        setProcessing(true);
        const controller = new AbortController();
        setAbortController(controller);

        const assistantMessageId = addMessage({
            role: "assistant",
            content: "",
            streaming: true,
        }).id;

        try {
            await streamChat(
                text || "这是我冰箱里的食物，帮我看看能做什么佳肴？",
                (chunk) => {
                    setMessages((prev) =>
                        prev.map((msg) =>
                            msg.id === assistantMessageId
                                ? {...msg, content: msg.content + chunk}
                                : msg
                        )
                    );
                },
                imageUrl,
                (error) => {
                    console.error("聊天失败:", error);
                    setMessages((prev) =>
                        prev.map((msg) =>
                            msg.id === assistantMessageId
                                ? {
                                    ...msg,
                                    content: msg.content + `\n[错误]: ${error.message}`,
                                    streaming: false,
                                }
                                : msg
                        )
                    );
                },
                () => {
                    setMessages((prev) =>
                        prev.map((msg) =>
                            msg.id === assistantMessageId
                                ? {...msg, streaming: false}
                                : msg
                        )
                    );
                },
                threadId,
                "default",
                location?.lon,
                location?.lat,
                controller,
            );
        } finally {
            setProcessing(false);
            setAbortController(null);
        }
    };

    // 处理食谱反馈（拒绝按钮）
    const handleReject = (recipeName: string) => {
        setFeedbackRecipe(recipeName);
        setFeedbackOpen(true);
    };

    // 中止回答
    const handleAbort = () => {
        if (abortController) {
            abortController.abort();
            setAbortController(null);
            addMessage({
                role: "assistant",
                content: "回答已终止",
            });
        }
    };

    // 处理提醒设置更新
    const handleUpdateReminderSetting = async (reminderType: string, reminderName: string, enabled: boolean) => {
        try {
            await updateReminderSetting("default", reminderType, reminderName, enabled);
            setReminderSettings(prev => ({
                ...prev,
                [`${reminderType}_${reminderName}`]: enabled
            }));
        } catch (error) {
            console.error("更新提醒设置失败:", error);
        }
    };

    // 处理关闭提醒
    const handleDismissReminder = async (reminderId: number, permanently: boolean) => {
        try {
            await dismissReminder({reminderId, permanentlyDismiss: permanently}, "default");
            loadReminders();
        } catch (error) {
            console.error("关闭提醒失败:", error);
        }
    };

    return (
        <div className="min-h-screen relative">
            {/* 节日提醒窗口 - 左上角 */}
            {reminders.length > 0 && (
                <div className="fixed top-4 left-4 z-50 bg-white/90 backdrop-blur-sm rounded-lg shadow-lg border border-white/50 p-4 max-w-sm">
                    <div className="flex items-start justify-between mb-2">
                        <h3 className="font-semibold text-gray-800">节日提醒</h3>
                        <button
                            onClick={() => setReminderSettingsOpen(true)}
                            className="text-blue-500 hover:text-blue-700 text-sm"
                        >
                           设置的按钮
                        </button>
                    </div>
                    <div className="space-y-2">
                        {reminders.map((reminder: any) => (
                            <div key={reminder.id} className="flex items-center justify-between">
                                <span className="text-sm text-gray-700">{reminder.message}</span>
                                <button
                                    onClick={() => handleDismissReminder(reminder.id, false)}
                                    className="text-gray-400 hover:text-gray-600 text-xs"
                                >
                                    关闭
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* 提醒设置面板 */}
            {reminderSettingsOpen && (
                <ReminderSettingsPanel
                    settings={reminderSettings}
                    onClose={() => setReminderSettingsOpen(false)}
                    onUpdateSetting={handleUpdateReminderSetting}
                />
            )}

            {/* RAG 面板 */}
            <RAGPanel onClose={() => setRagOpen(false)} />

            {/* 背景 */}
            <div className="fixed inset-0 bg-gradient-to-br from-blue-50 via-sky-50 to-indigo-50"/>
            <div className="fixed inset-0 opacity-30">
                <div className="absolute top-20 left-10 w-72 h-72 bg-blue-200 rounded-full mix-blend-multiply filter blur-xl animate-pulse"/>
                <div className="absolute top-40 right-10 w-96 h-96 bg-sky-200 rounded-full mix-blend-multiply filter blur-xl animate-pulse" style={{animationDelay: '1s'}}/>
                <div className="absolute bottom-20 left-1/3 w-80 h-80 bg-indigo-100 rounded-full mix-blend-multiply filter blur-xl animate-pulse" style={{animationDelay: '2s'}}/>
            </div>

            {/* 固定顶部标题栏 */}
            <header className="fixed top-0 left-0 right-0 z-50 p-4">
                <div className="max-w-4xl mx-auto bg-white/80 backdrop-blur-sm rounded-2xl shadow-lg border border-white/50 px-6 py-4 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-gradient-to-br from-blue-500 to-indigo-500 rounded-xl">
                            <ChefHat className="text-white" size={24}/>
                        </div>
                        <div>
                            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">AI 私人厨师</h1>
                            <p className="text-sm text-gray-500">上传食材图片，获取个性化食谱推荐</p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={handleGetLocation}
                            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl transition-colors text-sm ${
                                location
                                    ? "bg-blue-100 text-blue-700"
                                    : "bg-gray-100 text-gray-600 hover:bg-blue-50 hover:text-blue-600"
                            }`}
                            disabled={locationLoading}
                        >
                            <MapPin size={16} className={locationLoading ? "animate-pulse" : ""}/>
                            <span>{location ? "已定位" : locationLoading ? "定位中..." : "定位"}</span>
                        </button>
                        <button
                            onClick={handleNewChat}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-xl transition-colors"
                        >
                            <Plus size={18}/>
                            <span>新建会话</span>
                        </button>

                    </div>
                </div>
            </header>

            {/* 主内容区域 */}
            <div className="relative flex flex-col min-h-screen max-w-4xl mx-auto px-4 pt-24 pb-24">
                {/* 聊天区域 */}
                <div className="flex-1 bg-white/60 backdrop-blur-sm rounded-2xl shadow-lg border border-white/50 overflow-hidden flex flex-col">
                    <div className="flex-1 overflow-y-auto p-4">
                        {messages.length === 0 ? (
                            <div className="h-full flex flex-col items-center justify-center text-gray-400 mt-3">
                                <div className="p-4 bg-white/80 rounded-full mb-4">
                                    <UtensilsCrossed size={48} className="text-blue-400"/>
                                </div>
                                <p className="text-lg font-medium text-gray-600">上传食材图片开始吧</p>
                                <p className="text-sm mt-2 text-gray-400">我会帮您识别食材并推荐食谱</p>
                                <div className="mt-6 flex gap-3">
                                    <div className="px-4 py-2 bg-blue-50 rounded-lg text-sm text-blue-600 cursor-pointer hover:bg-blue-100 transition-colors"
                                         onClick={() => handleSend("冰箱里有鸡蛋、番茄和青椒，帮我推荐菜谱")}>
                                        鸡蛋+番茄+青椒
                                    </div>
                                    <div className="px-4 py-2 bg-blue-50 rounded-lg text-sm text-blue-600 cursor-pointer hover:bg-blue-100 transition-colors"
                                         onClick={() => handleSend("今天晚饭吃什么好？简单快手就行")}>
                                        简单快手晚餐
                                    </div>
                                    <div className="px-4 py-2 bg-blue-50 rounded-lg text-sm text-blue-600 cursor-pointer hover:bg-blue-100 transition-colors"
                                         onClick={() => handleSend("最近有点上火了，推荐清淡食谱")}>
                                        清淡食谱
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {messages.map((message) => (
                                    <ChatMessage key={message.id} message={message} onReject={handleReject}/>
                                ))}
                                <div ref={messagesEndRef}/>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* 固定底部输入区域 */}
            <div className="fixed bottom-0 left-0 right-0 z-50 p-4">
                <div className="max-w-4xl mx-auto bg-white/80 backdrop-blur-sm rounded-2xl shadow-lg border border-white/50">
                    <ChatInput onSend={handleSend} disabled={processing} onAbort={handleAbort} aborting={!!abortController}/>
                </div>
            </div>

            {/* 反馈弹窗 */}
            <FeedbackDialog
                open={feedbackOpen}
                recipeName={feedbackRecipe}
                threadId={threadId}
                onClose={() => setFeedbackOpen(false)}
            />
        </div>
    );
}