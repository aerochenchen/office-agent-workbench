/** User-facing product guide — welcome, micro-hints, and settings「使用说明」. */

import { STUDIO_NAME } from "./brand";

export interface GuidePillar {
  id: string;
  title: string;
  /** Short copy for the welcome screen. */
  summary: string;
  /** Full copy for settings「使用说明」. */
  body: string;
}

/** One clickable office task under a capability branch. */
export interface CapabilityLeaf {
  id: string;
  /** Short name in the capability tree. */
  label: string;
  /** Full phrasing filled into the composer. */
  saying: string;
}

/** Top-level branch in the official 办事能力 tree (shell catalog, not skills). */
export interface CapabilityBranch {
  id: string;
  label: string;
  children: readonly CapabilityLeaf[];
}

export const FORBIDDEN_USER_TERMS = ["工作区", "项目文件夹"] as const;

/** Core advantages: brief on welcome, full text in settings. */
export const GUIDE_PILLARS: readonly GuidePillar[] = [
  {
    id: "local",
    title: "本地可控",
    summary: "选定文件夹后，只在这里读取、整理、写作。",
    body:
      "选定文件夹后，原始材料、参考信息和成果都放在这里。文书通只在这个文件夹里读取、整理、写作。",
  },
  {
    id: "privacy",
    title: "尊重隐私",
    summary: "记录和材料留在本机，开发者不收集。",
    body:
      "聊天记录、原始材料和成果都留在本机。文书通没有自己的服务器，开发者不收集用户信息。",
  },
  {
    id: "forms",
    title: "文数皆通",
    summary: "文字、数字和图表，都可以试一试。",
    body:
      "文字、数字和图表，以这三种形式为载体的知识、信息、资料都可以试一试用文书通处理。",
  },
  {
    id: "method",
    title: "方法沉淀",
    summary: "好流程固化成技能，经验留得下来。",
    body:
      "把反复验证过的工作方法与流程固化成技能：规则写清、重活脚本化，安装后可反复调用。将经验留存，而不是每次重新再来。",
  },
] as const;

export const GUIDE_WELCOME_TITLE = "认识文书通";

/** Empty-chat headline when no folder is open. */
export const GUIDE_EMPTY_HEADLINE_NO_FOLDER = "打开文件夹，一句话开始办事";
/** Empty-chat headline when a folder is already open. */
export const GUIDE_EMPTY_HEADLINE_WITH_FOLDER = "一句话开始办事";

export function guideEmptyHeadline(workspaceOpen: boolean): string {
  return workspaceOpen
    ? GUIDE_EMPTY_HEADLINE_WITH_FOLDER
    : GUIDE_EMPTY_HEADLINE_NO_FOLDER;
}

/**
 * Official 办事能力 tree — grounded in agent primitives (folder read/write,
 * Office extract, draft/rewrite, scripted methods), shown as office scenarios.
 * Not derived from installed skills; skills remain a management-layer concept.
 */
export const CAPABILITY_TREE: readonly CapabilityBranch[] = [
  {
    id: "drafting",
    label: "文章写作",
    children: [
      {
        id: "format-gongwen",
        label: "公文排版",
        saying: "把这份稿按公文格式排好",
      },
      {
        id: "proofread",
        label: "通篇校对",
        saying: "通篇校对术语、数字和称谓",
      },
      {
        id: "draft-rewrite",
        label: "起草与改写",
        saying: "按这个提纲起草一稿，语气正式一些",
      },
      {
        id: "template-fill-doc",
        label: "按模板补全",
        saying: "按这个模板，用文件夹里的材料把内容补全",
      },
    ],
  },
  {
    id: "review",
    label: "对照审校",
    children: [
      {
        id: "revision-diff",
        label: "两版对比",
        saying: "两版对比，列出主要改动",
      },
      {
        id: "clause-compare",
        label: "条款对照",
        saying: "对照范本看条款改了哪些",
      },
      {
        id: "term-unify",
        label: "术语统一",
        saying: "把文中的单位名称和术语统一一遍",
      },
    ],
  },
  {
    id: "materials",
    label: "材料汇总",
    children: [
      {
        id: "multidoc-digest",
        label: "多份汇总",
        saying: "多份材料汇总成带出处的报告",
      },
      {
        id: "extract-points",
        label: "抽取要点",
        saying: "把这份材料里的要点摘出来备用",
      },
      {
        id: "folder-survey",
        label: "文件夹摸底",
        saying: "看看当前文件夹里有哪些材料，按类型列个清单",
      },
    ],
  },
  {
    id: "meeting",
    label: "会议督办",
    children: [
      {
        id: "minutes",
        label: "整理纪要",
        saying: "根据这份记录整理成会议纪要",
      },
      {
        id: "action-items",
        label: "待办分人",
        saying: "根据纪要整理待办并分给人",
      },
      {
        id: "follow-up",
        label: "催办说明",
        saying: "根据待办台账写一份本周催办说明",
      },
    ],
  },
  {
    id: "data",
    label: "表格成文",
    children: [
      {
        id: "excel-brief",
        label: "表写情况说明",
        saying: "用这张表写一段情况说明",
      },
      {
        id: "data-insights",
        label: "数据结论",
        saying: "解读这张表，写出几条主要结论",
      },
      {
        id: "form-fill",
        label: "按表填报",
        saying: "按这个空白表，用文件夹里的材料填好",
      },
      {
        id: "chart-generation",
        label: "图表生成",
        saying: "把这张表做成最合适的图表，方便汇报展示",
      },
    ],
  },
  {
    id: "present",
    label: "汇报演示",
    children: [
      {
        id: "ppt-palette",
        label: "正式配色",
        saying: "给 PPT 选一套正式汇报配色",
      },
      {
        id: "ppt-outline",
        label: "汇报提纲",
        saying: "按这份材料整理成汇报提纲，适合做成幻灯片",
      },
      {
        id: "ppt-deck-and-script",
        label: "演示文稿",
        saying: "根据这份材料生成一套 PPT，并写一份对应的汇报稿",
      },
    ],
  },
  {
    id: "beyond",
    label: "举一反三",
    children: [
      {
        id: "one-to-three",
        label: "一文三用",
        saying: "同一批材料，分别整理成报告正文、汇报提纲和答问口径",
      },
      {
        id: "red-pen-review",
        label: "红笔找茬",
        saying: "站在审稿领导的角度，把这篇里站不住、易被追问的地方标出来",
      },
      {
        id: "gap-checklist",
        label: "缺啥补啥",
        saying: "对照要写的题目，列出文件夹里还缺哪些关键材料",
      },
      {
        id: "plan-resume",
        label: "继续工作计划",
        saying: "按工作计划未完成项继续",
      },
    ],
  },
] as const;

export function listCapabilityLeaves(): CapabilityLeaf[] {
  return CAPABILITY_TREE.flatMap((b) => [...b.children]);
}

/** Footer of settings「使用说明」, with the studio WeChat Channels QR. */
export const GUIDE_MORE_HELP = `更多使用说明，请查看微信视频号「${STUDIO_NAME}」。`;

export const GUIDE_HINTS = {
  bootWaiting: "首次启动约需数秒，请稍候。",
  noSessions: "暂无对话。点击上方「新建对话」开始。",
  noSkills: "可导入本地技能包增强能力；安装与运行均在本机。",
  noEnabledSkills: "暂无启用中的技能；可在技能管理中启用或导入。",
  newSessionNeedsFolder: "打开文件夹后可新建并保存对话",
} as const;

export const MODEL_SETUP_REPLY =
  "要开始对话，需要先连上大模型。请打开右上角「设置」，填写 API 地址和模型名。" +
    "公网接口还需填写 API Key（密钥）；本机或内网服务若不校验密钥，可留空。" +
    "材料仍在你的本机；配置的是你自己的接口。配好后，直接在下方再发一句即可。";

export function needsModelSetup(config: {
  api_base?: string;
  api_key_set?: boolean;
  deployment_profile?: string;
}): boolean {
  const apiBase = (config.api_base || "").trim();
  if (config.deployment_profile === "local") {
    return !apiBase;
  }
  return !config.api_key_set;
}

/** Model/auth setup failures → show MODEL_SETUP_REPLY; not runtime connectivity. */
export function isModelSetupError(message: string): boolean {
  return /API Key|未配置|api key|401|403/i.test(message);
}
