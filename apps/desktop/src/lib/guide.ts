/** User-facing product guide — welcome, micro-hints, and settings「使用说明」. */

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
    summary: "材料在文件夹里办，用什么模型自己定。",
    body:
      "选定文件夹后，材料在本机该文件夹内读取与生成，不越界到文件夹外。大模型接口由你在设置中自行配置（地址、密钥、模型名），不绑定某一家公网云服务。",
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
      "把反复验证过的工作方法与流程固化成技能：规则写清、重活脚本化，安装后可反复调用。"
      + "单位称谓与术语可写入文件夹内 `.office-agent/glossary.md`，校对与起草时对照使用。"
      + "经验留在单位里，而不是每次从零写提示词。",
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

/** Empty-chat headline: one visual that signals breadth of capability. */
export const GUIDE_TRY_HEADLINE = "一句话开始办事";
/** @deprecated Kept for copy audits; UI no longer shows a separate subline. */
export const GUIDE_TRY_SUBLINE = "点一句填入下方，再按发送";

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
        label: "公文格式排版",
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
    ],
  },
] as const;

/** Featured leaf ids for the empty-chat grid (one main visual, not the full tree). */
const FEATURED_SAYING_IDS: readonly string[] = [
  "format-gongwen",
  "revision-diff",
  "multidoc-digest",
  "action-items",
  "excel-brief",
  "proofread",
  "ppt-palette",
  "clause-compare",
] as const;

function leafById(id: string): CapabilityLeaf | undefined {
  for (const branch of CAPABILITY_TREE) {
    const found = branch.children.find((c) => c.id === id);
    if (found) return found;
  }
  return undefined;
}

/** Flat featured sayings for the empty-chat main visual. */
export const GUIDE_TRY_SAYINGS: readonly string[] = FEATURED_SAYING_IDS.map((id) => {
  const leaf = leafById(id);
  if (!leaf) throw new Error(`FEATURED_SAYING_IDS missing leaf: ${id}`);
  return leaf.saying;
});

export function listCapabilityLeaves(): CapabilityLeaf[] {
  return CAPABILITY_TREE.flatMap((b) => [...b.children]);
}

export const GUIDE_HINTS = {
  noWorkspace: "打开文件夹后，对话与成果会保存在本地；办事时文书通只在该文件夹内读写。",
  /** Under empty-chat featured sayings when no folder is open. */
  emptyChat: "要排版、汇总等办事，请先打开文件夹",
  /** Under empty-chat featured sayings when a folder is already open. */
  workspaceReady: "开聊后可在右侧浏览全部分类",
  /** Right rail while empty chat — avoid duplicating the middle featured list. */
  capabilityTreeIdle: "先在中间选一句开始。开聊后，这里展示完整分类。",
  bootWaiting: "首次启动约需数秒，请稍候。",
  noSessions: "暂无对话。点击上方「新建对话」开始。",
  noSkills: "可导入本地技能包增强能力；安装与运行均在本机。",
  noEnabledSkills: "暂无启用中的技能；可在技能管理中启用或导入。",
  newSessionNeedsFolder: "打开文件夹后可新建并保存对话",
} as const;

export const MODEL_SETUP_REPLY =
  "要开始对话，需要先连上大模型。请打开右上角「设置」，填写 API 地址、API Key（密钥）和模型名。" +
    "材料仍在你的本机；配置的是你自己的接口。配好后，直接在下方再发一句即可。";

/** Model/auth setup failures → show MODEL_SETUP_REPLY; not runtime connectivity. */
export function isModelSetupError(message: string): boolean {
  return /API Key|未配置|api key|401|403/i.test(message);
}
