/** User-facing product guide — welcome, micro-hints, and settings「使用说明」. */

export interface GuidePillar {
  id: string;
  title: string;
  /** Short copy for the welcome screen. */
  summary: string;
  /** Full copy for settings「使用说明」. */
  body: string;
}

/** Three pillars: brief on welcome, full text in settings. */
export const GUIDE_PILLARS: readonly GuidePillar[] = [
  {
    id: "local",
    title: "本地闭环",
    summary: "文件与记录留在本机；只连内网模型做思考，不上传工作区文件。",
    body:
      "初始文件、过程文件与导出结果均在本机生成与读写；聊天与工作记录也保存在本地。不连接公网云服务；仅按设置访问单位内网模型做思考处理，交互为文本指令与结果，不把工作区文件上传到互联网或内网服务器。",
  },
  {
    id: "skills",
    title: "可扩展能力",
    summary: "可处理 Word / Excel / PPT；更强能力通过本地导入技能包扩展。",
    body:
      "已具备读取、分析与生成 Word、Excel、PPT 等常见办公文档的能力。更强能力可通过安装技能（Skill）扩展；技能包在本地导入安装，编写或获取后于本机使用，运行过程不连通公网。",
  },
  {
    id: "project",
    title: "文件夹 = 项目",
    summary: "选定文件夹后只在其内读写；重开同目录可续上工作进度。",
    body:
      "日常办公常把一项事务相关材料归集到同一文件夹。文书通同样聚焦于你选定的工作文件夹：只在其内读取、分析与生成，不越界影响文件夹外的文件。同一文件夹还会保留工作成果与进度，再次打开时可续上过往记录，保证工作独立、安全且连贯。",
  },
] as const;

export const GUIDE_WELCOME_TITLE = "认识文书通";

export const GUIDE_HINTS = {
  noWorkspace: "请选择本次工作的项目文件夹；文书通只在该文件夹内读写。",
  workspaceReady: "在本项目文件夹内描述任务即可；对话与成果会留在本地。",
  noSessions: "暂无对话。点击上方「新建对话」开始本项目工作。",
  noSkills: "可导入本地技能包增强能力；安装与运行均在本机。",
} as const;
