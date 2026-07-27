/** User-facing product guide — welcome, micro-hints, and settings「使用说明」. */

export interface GuidePillar {
  id: string;
  title: string;
  /** Short copy for the welcome screen. */
  summary: string;
  /** Full copy for settings「使用说明」. */
  body: string;
}

/** Core advantages: brief on welcome, full text in settings. */
export const GUIDE_PILLARS: readonly GuidePillar[] = [
  {
    id: "local",
    title: "本地可控",
    summary: "材料在文件夹里办，用什么模型自己定。",
    body:
      "选定工作区后，材料在本机文件夹内读取与生成，不越界到文件夹外。大模型接口由你在设置中自行配置（地址、密钥、模型名），不绑定某一家公网云服务。",
  },
  {
    id: "light",
    title: "轻量可跑",
    summary: "标准包轻，老旧机也能用。",
    body:
      "标准安装包刻意做薄，面向日常办公电脑与配置一般的老旧机；对话与轻量技能即可开箱使用。更重的能力（如本地检索写作）按需选装，不拖垮全员机器。",
  },
  {
    id: "method",
    title: "方法沉淀",
    summary: "好流程变成可复用技能。",
    body:
      "把反复验证过的工作方法与流程固化成技能：规则写清、重活脚本化，安装后可反复调用。经验留在单位里，而不是每次从零写提示词。",
  },
  {
    id: "skills",
    title: "能力插拔",
    summary: "专项技能可安装、可分享。",
    body:
      "排版、汇总、写作等专项能力以技能包形式提供，可在本机灵活安装、启停与分享。底座统一，能力按岗位与场景叠加。",
  },
] as const;

export const GUIDE_WELCOME_TITLE = "认识文书通";

export const GUIDE_HINTS = {
  noWorkspace: "请选择本次工作的项目文件夹；文书通只在该文件夹内读写。",
  workspaceReady: "在本项目文件夹内描述任务即可；对话与成果会留在本地。",
  noSessions: "暂无对话。点击上方「新建对话」开始本项目工作。",
  noSkills: "可导入本地技能包增强能力；安装与运行均在本机。",
  noEnabledSkills: "暂无启用中的技能；可在技能管理中启用或导入。",
} as const;
