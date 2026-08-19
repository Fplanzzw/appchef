"use client";

import { useState } from "react";
import { X } from "lucide-react";

interface ReminderSettingsPanelProps {
    settings: Record<string, boolean>;
    onClose: () => void;
    onUpdateSetting: (reminderType: string, reminderName: string, enabled: boolean) => void;
}

export default function ReminderSettingsPanel({ settings, onClose, onUpdateSetting }: ReminderSettingsPanelProps) {
    const [localSettings, setLocalSettings] = useState(settings);

    const toggleSetting = (key: string, enabled: boolean) => {
        setLocalSettings(prev => ({
            ...prev,
            [key]: enabled
        }));
        const [reminderType, reminderName] = key.split('_');
        onUpdateSetting(reminderType, reminderName, enabled);
    };

    const festivalReminders = {
        "春节": "春节快乐！阖家团圆，美食相伴！",
        "元宵节": "元宵佳节，吃汤圆，赏花灯！",
        "清明节": "清明时节，慎终追远，踏青郊游！",
        "端午节": "端午安康！粽子飘香，龙舟竞渡！",
        "七夕节": "七夕浪漫！与心爱的人共进美食！",
        "中秋节": "中秋佳节，月饼配茶，温馨团圆！",
        "重阳节": "重阳登高，敬老爱老，重阳糕正当时！",

        "腊八节": "腊八节到了！喝一碗腊八粥，温暖一整年！",
        "小年": "小年到！祭灶糖瓜甜，扫尘迎新年！"
    };

    const seasonalReminders = {
        "春季": "春季温和，推荐清淡养胃的菜谱，如山药炒木耳、清蒸鲈鱼。",
        "夏季": "夏季炎热，推荐降火消暑的菜谱，如绿豆汤、凉拌黄瓜、冬瓜排骨汤、杨枝甘露甜品。",
        "秋季": "秋季凉爽干燥，推荐润肺养胃的菜谱，如百合银耳汤、莲子百合粥、白萝卜炖排骨。",
        "冬季": "冬季寒冷，推荐暖身滋补的菜谱，当归羊肉汤、白萝卜炖排骨、红枣枸杞鸡汤。"
    };

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto">
                <div className="p-6">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-2xl font-bold text-gray-800">提醒设置</h2>
                        <button
                            onClick={onClose}
                            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                        >
                            <X size={24} className="text-gray-600"/>
                        </button>
                    </div>

                    <div className="space-y-6">
                        {/* 节日提醒设置 */}
                        <div>
                            <h3 className="text-lg font-semibold text-gray-700 mb-4">节日提醒</h3>
                            <div className="space-y-3">
                                {Object.entries(festivalReminders).map(([festival, message]) => {
                                    const key = `festival_${festival}`;
                                    const enabled = localSettings[key] ?? true;
                                    return (
                                        <div key={festival} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                                            <div>
                                                <div className="font-medium text-gray-800">{festival}</div>
                                                <div className="text-sm text-gray-600">{message}</div>
                                            </div>
                                            <label className="flex items-center gap-2 cursor-pointer">
                                                <input
                                                    type="checkbox"
                                                    checked={enabled}
                                                    onChange={(e) => toggleSetting(key, e.target.checked)}
                                                    className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                                                />
                                                <span className="text-sm text-gray-700">
                                                    {enabled ? "已开启" : "已关闭"}
                                                </span>
                                            </label>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        {/* 季节性提醒设置 */}
                        <div>
                            <h3 className="text-lg font-semibold text-gray-700 mb-4">季节性提醒</h3>
                            <div className="space-y-3">
                                {Object.entries(seasonalReminders).map(([season, message]) => {
                                    const key = `seasonal_${season}`;
                                    const enabled = localSettings[key] ?? true;
                                    return (
                                        <div key={season} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                                            <div>
                                                <div className="font-medium text-gray-800">{season}</div>
                                                <div className="text-sm text-gray-600">{message}</div>
                                            </div>
                                            <label className="flex items-center gap-2 cursor-pointer">
                                                <input
                                                    type="checkbox"
                                                    checked={enabled}
                                                    onChange={(e) => toggleSetting(key, e.target.checked)}
                                                    className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                                                />
                                                <span className="text-sm text-gray-700">
                                                    {enabled ? "已开启" : "已关闭"}
                                                </span>
                                            </label>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        {/* 用户画像更新设置 */}
                        <div>
                            <h3 className="text-lg font-semibold text-gray-700 mb-4">用户画像更新</h3>
                            <div className="p-3 bg-gray-50 rounded-lg">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <div className="font-medium text-gray-800">每周用户画像更新</div>
                                        <div className="text-sm text-gray-600">每周一凌晨自动更新用户口味偏好</div>
                                    </div>
                                    <label className="flex items-center gap-2 cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={localSettings["profile_update"] ?? true}
                                            onChange={(e) => toggleSetting("profile_update", e.target.checked)}
                                            className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
                                        />
                                        <span className="text-sm text-gray-700">
                                            {localSettings["profile_update"] ?? true ? "已开启" : "已关闭"}
                                        </span>
                                    </label>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}