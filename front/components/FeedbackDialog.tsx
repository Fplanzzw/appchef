/**
 * 食谱反馈弹窗 — 用于拒绝菜谱并补充说明
 */
import {useState} from "react";
import {X, MessageCircle} from "lucide-react";
import {sendRecipeFeedback} from "@/lib/api";

interface FeedbackDialogProps {
    open: boolean;
    recipeName: string;
    threadId: string;
    onClose: () => void;
}

export function FeedbackDialog({open, recipeName, threadId, onClose}: FeedbackDialogProps) {
    const [clarification, setClarification] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [result, setResult] = useState<string | null>(null);

    if (!open) return null;

    const handleReject = async () => {
        setSubmitting(true);
        try {
            const res = await sendRecipeFeedback(threadId, "reject", {recipeName});
            if (res.phase === "swap_same_category") {
                setResult(`已记录拒绝「${recipeName}」，下次会推荐同类食材不同做法。`);
            } else if (res.phase === "reflection_question") {
                setResult(res.question || "请补充说明你不喜欢的食材或口味。");
            }
        } catch (e) {
            setResult("反馈失败，请稍后重试。");
        } finally {
            setSubmitting(false);
        }
    };

    const handleClarify = async () => {
        if (!clarification.trim()) return;
        setSubmitting(true);
        try {
            const res = await sendRecipeFeedback(threadId, "clarify", {
                userClarification: clarification.trim(),
            });
            if (res.ok) {
                setResult("已记录您的偏好，下次推荐会更贴合口味！");
            } else {
                setResult("提交失败，请重试。");
            }
        } catch (e) {
            setResult("提交失败，请重试。");
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full mx-4 overflow-hidden">
                <div className="flex items-center justify-between p-4 border-b border-gray-100">
                    <div className="flex items-center gap-2">
                        <MessageCircle size={20} className="text-blue-500"/>
                        <h3 className="font-semibold text-gray-800">菜谱反馈</h3>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                        <X size={18} className="text-gray-400"/>
                    </button>
                </div>

                <div className="p-4">
                    <p className="text-gray-600 mb-4">
                        你对「<span className="font-medium text-blue-600">{recipeName}</span>」不满意？
                    </p>

                    {!result ? (
                        <>
                            <div className="flex gap-2 mb-4">
                                <button
                                    onClick={handleReject}
                                    disabled={submitting}
                                    className="flex-1 px-4 py-2.5 bg-blue-500 text-white rounded-xl hover:bg-blue-600 disabled:opacity-50 transition-colors text-sm font-medium"
                                >
                                    {submitting ? "提交中..." : "换一道菜"}
                                </button>
                            </div>
                            <div className="border-t border-gray-100 pt-4">
                                <p className="text-sm text-gray-500 mb-2">或者告诉我们更具体的偏好：</p>
                                <textarea
                                    value={clarification}
                                    onChange={(e) => setClarification(e.target.value)}
                                    placeholder="例如：不吃海鲜、口味偏清淡、对花生过敏..."
                                    className="w-full bg-gray-50 border-0 rounded-xl px-3 py-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-blue-300 text-sm"
                                    rows={3}
                                />
                                <button
                                    onClick={handleClarify}
                                    disabled={submitting || !clarification.trim()}
                                    className="mt-2 w-full px-4 py-2.5 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
                                >
                                    {submitting ? "提交中..." : "提交偏好说明"}
                                </button>
                            </div>
                        </>
                    ) : (
                        <div className="bg-blue-50 rounded-xl p-4 mb-4">
                            <p className="text-sm text-blue-700">{result}</p>
                        </div>
                    )}
                </div>

                <div className="p-4 border-t border-gray-100">
                    <button
                        onClick={onClose}
                        className="w-full px-4 py-2.5 bg-gray-100 text-gray-600 rounded-xl hover:bg-gray-200 transition-colors text-sm"
                    >
                        关闭
                    </button>
                </div>
            </div>
        </div>
    );
}
