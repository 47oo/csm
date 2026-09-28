// 固定枚举本地模糊匹配（架构 F008 §4.2/§5.4，需求 §8.1/§8.2）：
// - 输入去首尾空格、英文不区分大小写；
// - 命中中文展示名或英文代码即匹配；rank 阶梯：完全 1 < 前缀 2 < 包含 4
//   （与 §8.2 服务端权重一致，用于本地排序；同级保持原选项顺序稳定）；
// - 适用于 resource_type / status / 角色等前端代码内枚举映射，无后端，不新增取值。

/** 文本 rank：完全 1 / 前缀 2 / 包含 4；未命中返回 null（入参须已归一：去空格、小写） */
function textRank(value: string, needle: string): number | null {
  if (value === needle) return 1
  if (value.startsWith(needle)) return 2
  if (value.includes(needle)) return 4
  return null
}

/**
 * 枚举匹配（架构 F008 §4.2 `enumSearch.match(label, code, input)`）：
 * 归一输入（去首尾空格、英文不区分大小写）后，对中文展示名与英文代码分别计算
 * rank 并取最小；未命中返回 null。空输入（含仅空白）不匹配（= 不过滤）。
 */
export function match(label: string, code: string, input: string): number | null {
  const needle = input.trim().toLowerCase()
  if (needle === '') return null
  let best: number | null = null
  for (const rank of [textRank(label.toLowerCase(), needle), textRank(code.toLowerCase(), needle)]) {
    if (rank !== null && (best === null || rank < best)) best = rank
  }
  return best
}

/** 枚举选项（value=英文代码，label=中文展示名） */
export interface EnumSearchOption {
  value: string
  label: string
}

/**
 * 过滤并按 rank 稳定排序（rank 相同保持原选项顺序）：
 * 空输入（含仅空白）返回全部选项（= 初始候选）。
 */
export function filterEnumOptions(options: EnumSearchOption[], input: string): EnumSearchOption[] {
  const needle = input.trim().toLowerCase()
  if (needle === '') return options
  const ranked: Array<{ option: EnumSearchOption; rank: number }> = []
  for (const option of options) {
    const rank = match(option.label, option.value, input)
    if (rank !== null) ranked.push({ option, rank })
  }
  return ranked.sort((a, b) => a.rank - b.rank).map((r) => r.option)
}
