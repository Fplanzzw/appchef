/**
 * 节日提醒组件 - 左上角小窗口
 */
import {useState, useEffect} from "react";
import {Bell, X} from "lucide-react";

interface FestivalReminderProps {
    onClose: () => void;
}

export function FestivalReminder({onClose}: FestivalReminderProps) {
    const [show, setShow] = useState(true);
    const [festival, setFestival] = useState("冬至");
    const [message, setMessage] = useState("冬至到了！记得吃饺子哦～");
    const [enabled, setEnabled] = useState(true);

    // 模拟节日提醒（实际应从后端获取）
    useEffect(() => {
        // 这里简化：根据当前日期模拟不同节日
        const now = new Date();
        const month = now.getMonth() + 1;
        const day = now.getDate();
        
        if (month === 12 && day === 22) {
            setFestival("冬1至");
            setMessage("冬至到了！记得吃饺子哦～");
        } else if (month === 2 && day === 10) {
            setFestival("春节");
            setMessage("春节快乐！阖家团圆，美食相伴！");
        } else if (month === 9 && day === 29) {
            setFestival("中秋节");
            setMessage("中秋佳节，月饼配茶，温馨团圆！");
        } else if (month === 6 && day === 10) {
            setFestival("端午节");
            setMessage("端午安康！粽子飘香，龙舟竞渡！");
        } else {
            // 非节日时显示即将到来的节日
            setFestival("");
        setMessage("最近没有节日，想好吃什么了吗？");
                }
            }
        }
    }, []);

    if (!show || !enabled) return null;

    return (
        <div className="fixed top-4 left-4 z-[200] bg-gradient-to-r from-blue-500 to-indigo-500 text-white rounded-xl shadow-xl p-4 max-w-xs">
            <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-2">
                    <Bell size={18} className="text-yellow-300"/>
                    <span className="font-semibold">节日提醒</span>
                </div>
                <button
                    onClick={onClose}
                    className="p-1 hover:bg-white/20 rounded-lg transition-colors"
                >
                    <X size={16} className="text-white/80"/>
                </button>
            </div>
            <div className="mb-3">
                <p className="font-medium">{festival}</p>
                <p className="text-sm opacity-90">{message}</p>
            </div>
            <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-sm">
                    <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(e) => setEnabled(e.target.checked)}
                        className="rounded border-white/30 bg-white/20 text-blue-600 focus:ring-blue-300"
                    />
                    <span>开启提醒</span>
                </label>
                <button
                    onClick={onClose}
                    className="px-3 py-1 bg-white/20 hover:bg-white/30 rounded-lg text-sm transition-colors"
                >
                    关闭
                </button>
            </div>
        </div>
    );
}