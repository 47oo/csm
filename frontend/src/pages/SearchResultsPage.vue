<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { searchClusterResources } from '../api/search'
import type { ResourceRef, SearchResultRow, SearchResourceType } from '../api/search'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import ListStates from '../components/ListStates.vue'

/**
 * 搜索结果页（F019 聚合视图，R-QUERY-006 / AC-A1~A8；F018 产品页升级）。
 *
 * - 调用 GET /api/clusters/{cluster_id}/search（f019 契约 §3，唯一搜索端点）：
 *   **单请求**获得「命中项 + 其关联链」的单一扁平行列表；本页不做任何浏览器
 *   端拼接 / 关联推导（架构 Handoff 裁定 1；关联链与推导路径均由后端给出）；
 * - 渲染按 items 原样顺序：相邻且 group_key 相同的行构成一个**组织单元**
 *   （契约 §2.2），单元首行为命中行、其后为关联行（AC-A8）：
 *   - 命中行（role == "HIT"）：徽标「命中」+ 标识字段（按类型取 hostname /
 *     name / ip_address，契约原样值）+ matched_fields 标签（契约原样字段名，
 *     不解释 / 不翻译）+「查看」入口；
 *   - 关联行（role == "RELATED"）：**缩进** + 徽标「关联」+ 由 derivation_path
 *     生成的路径文案（首 = 命中项、末 = 本行，如「IP 地址 10.0.1.1/16 →
 *     网络接口 eth0 → 裸金属 cn001」；文案为 Frontend 决定，架构 Handoff
 *     NQ-E）+「查看」入口；
 *   - 跨单元**不去重**（AC-A5）：同一资源因多条命中链重复出现时原样渲染
 *     多行，不合并；
 * - 三态互不相同（AC-07）：Loading（骨架屏）/ Empty（200 + items == []，
 *   「无匹配结果」，R-QUERY-004 Empty 语义，不得渲染为错误、不触发全局
 *   会话失效）/ Error（按 error.code 分支渲染，不解析 message：NOT_FOUND →
 *   「未找到资源」，VALIDATION_ERROR → 校验失败，NETWORK_ERROR → 连接失败）；
 * - 「查看」进入对应资源详情（复用 App 既有 open*Detail 导航，携带搜索
 *   视图为返回目标）；返回按钮回集群列表（与无过滤上下文的列表页一致）；
 * - 分页按**组织单元（命中项）计数**（f019 契约 §3 语义 4）：total = 单元数，
 *   len(items) 可大于 page_size；page_size 选项均在契约合法区间 [1, 200] 内，
 *   参数合法性由服务端校验。
 */
const props = defineProps<{
  /** 搜索范围：已选定的 Cluster id（R-QUERY-005 前置）。 */
  clusterId: number
  /** 搜索关键字（原样值，不 trim，f018 契约 §2）。 */
  keyword: string
}>()

const emit = defineEmits<{
  back: []
  openBareMetalDetail: [bareMetalId: number]
  openNetworkInterfaceDetail: [networkInterfaceId: number]
  openIpAddressDetail: [ipAddressId: number]
  openVirtualMachineDetail: [virtualMachineId: number]
  openContainerDetail: [containerId: number]
  openServiceDetail: [serviceId: number]
}>()

/** 分页状态（单元级）；page_size 选项均在契约合法区间 [1, 200] 内。 */
const page = ref(1)
const pageSize = ref(50)

const { data, loading, error, run } = useAsyncQuery(() =>
  searchClusterResources(props.clusterId, {
    keyword: props.keyword,
    page: page.value,
    page_size: pageSize.value,
  }),
)

const results = computed(() => data.value?.items ?? [])

/**
 * Loading 判定：请求进行中，或首次请求尚未返回（data 与 error 均为空）。
 * 后者避免首帧闪现空内容（与既有列表页同一模式）。
 */
const isLoading = computed(
  () => loading.value || (data.value === null && error.value === null),
)

/** Empty 判定：请求成功（data 非空）且 items 为空（契约 §6 Empty 语义）。 */
const listEmpty = computed(() => data.value !== null && data.value.items.length === 0)

/** 组织单元（命中项）全量数（契约 §4：total = 单元数，驱动分页）。 */
const total = computed(() => data.value?.total ?? 0)

/** resource_type 可读标签（六值封闭集合；与领域资源类型名一致，仅呈现）。 */
const RESOURCE_TYPE_LABELS: Record<SearchResourceType, string> = {
  BARE_METAL: '裸金属',
  NETWORK_INTERFACE: '网络接口',
  IP_ADDRESS: 'IP 地址',
  VIRTUAL_MACHINE: '虚拟机',
  CONTAINER: '容器',
  SERVICE: '服务',
}

/** 每类资源的标识字段值（契约原样值，不做任何变换）。 */
function identifierOf(item: SearchResultRow): string {
  switch (item.resource_type) {
    case 'BARE_METAL':
      return item.resource.hostname
    case 'NETWORK_INTERFACE':
      return item.resource.name
    case 'IP_ADDRESS':
      return item.resource.ip_address
    case 'VIRTUAL_MACHINE':
      return item.resource.name
    case 'CONTAINER':
      return item.resource.name
    case 'SERVICE':
      return item.resource.name
  }
}

/** 资源引用的稳定键：resource_type 封闭六值 + 类型内 id，跨类型不冲突。 */
function refKey(ref: ResourceRef): string {
  return `${ref.resource_type}:${ref.id}`
}

/**
 * 本页各行「资源引用 → 标识字段值」查找表（仅用于推导路径文案取途经资源的
 * 标识）。契约 §4.3：derivation_path 仅由单元内已物化资源组成，首尾与途经
 * 元素均为本页 items 内的行（单元不跨页拆散，契约 §3 语义 4），故查本页即可，
 * 不发起额外请求、不做任何浏览器端关联推导。
 */
const identifierByRefKey = computed(() => {
  const map = new Map<string, string>()
  for (const row of results.value) {
    map.set(refKey({ resource_type: row.resource_type, id: row.id }), identifierOf(row))
  }
  return map
})

/**
 * 组织单元首行索引：items 中 group_key 与前一行不同的行（契约 §2.2：相邻且
 * group_key 相同的行构成一个组织单元，首行为 HIT）。仅用于呈现（单元间分隔
 * 线），不重排 / 不合并行，跨单元不去重（AC-A5）。
 */
const groupStartIndexes = computed(() => {
  const starts = new Set<number>()
  let previousKey: string | null = null
  results.value.forEach((row, index) => {
    const key = refKey(row.group_key)
    if (key !== previousKey) {
      starts.add(index)
      previousKey = key
    }
  })
  return starts
})

/**
 * 关联行推导路径文案（AC-A2；文案由 Frontend 决定，架构 Handoff NQ-E）：
 * 由 derivation_path 各步的「类型标签 + 标识字段」用「 → 」连接，首元素 =
 * 本单元命中项、末元素 = 本行（契约 §4.1 / §4.3），按序原样渲染。
 * 途经引用未在本页出现时（不符合契约的响应）退化为「类型 #id」，不猜测。
 */
function derivationPathText(row: SearchResultRow): string {
  if (row.role !== 'RELATED' || row.derivation_path === null) return ''
  return row.derivation_path
    .map((step) => {
      const identifier = identifierByRefKey.value.get(refKey(step))
      const label = RESOURCE_TYPE_LABELS[step.resource_type]
      return identifier === undefined ? `${label} #${step.id}` : `${label} ${identifier}`
    })
    .join(' → ')
}

/** el-table 行类：关联行（缩进底色）与组织单元首行（分隔线），仅呈现。 */
function rowClassName({ row, rowIndex }: { row: SearchResultRow; rowIndex: number }): string {
  const classes: string[] = []
  if (row.role === 'RELATED') classes.push('search-results__row--related')
  // 首行上方已有表头分隔线，不再叠加（仅单元之间加分隔线）。
  if (rowIndex > 0 && groupStartIndexes.value.has(rowIndex)) {
    classes.push('search-results__row--group-start')
  }
  return classes.join(' ')
}

onMounted(() => {
  void run()
})

// App 侧再次发起搜索（同组件复用，如在外壳用同一页面重新触发）可能只改变
// clusterId / keyword：回到第 1 页并重新查询。
watch(
  () => [props.clusterId, props.keyword],
  () => {
    page.value = 1
    void run()
  },
)

function refresh(): void {
  void run()
}

function handlePageChange(next: number): void {
  page.value = next
  void run()
}

function handleSizeChange(size: number): void {
  pageSize.value = size
  page.value = 1
  void run()
}

function goBack(): void {
  emit('back')
}

/** 从结果行（命中行 / 关联行同权）进入对应资源详情（复用 App 既有 open*Detail）。 */
function openDetail(item: SearchResultRow): void {
  switch (item.resource_type) {
    case 'BARE_METAL':
      emit('openBareMetalDetail', item.id)
      break
    case 'NETWORK_INTERFACE':
      emit('openNetworkInterfaceDetail', item.id)
      break
    case 'IP_ADDRESS':
      emit('openIpAddressDetail', item.id)
      break
    case 'VIRTUAL_MACHINE':
      emit('openVirtualMachineDetail', item.id)
      break
    case 'CONTAINER':
      emit('openContainerDetail', item.id)
      break
    case 'SERVICE':
      emit('openServiceDetail', item.id)
      break
  }
}
</script>

<template>
  <main class="search-results" data-testid="search-results">
    <header class="search-results__header">
      <div class="search-results__nav">
        <el-button @click="goBack">返回集群列表</el-button>
        <h1 class="search-results__title">
          搜索结果
          <el-tag class="search-results__context" size="small">集群 #{{ clusterId }}</el-tag>
          <el-tag class="search-results__context" size="small" type="info">
            关键字「{{ keyword }}」
          </el-tag>
        </h1>
      </div>
      <div class="search-results__actions">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </header>

    <section class="search-results__body">
      <!-- 单一扁平聚合列表（AC-A1）：按 items 原样顺序渲染，不按 resource_type
           分区；相邻 group_key 相同的行构成一个组织单元（命中行 + 缩进关联行）。 -->
      <ListStates :loading="isLoading" :error="error" :empty="listEmpty" empty-description="无匹配结果">
        <el-table
          :data="results"
          :row-class-name="rowClassName"
          class="search-results__table"
          data-testid="search-results-table"
        >
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              <el-tag>{{ RESOURCE_TYPE_LABELS[(row as SearchResultRow).resource_type] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="标注" width="90">
            <template #default="{ row }">
              <el-tag
                v-if="(row as SearchResultRow).role === 'HIT'"
                type="success"
                data-testid="search-result-role"
              >
                命中
              </el-tag>
              <el-tag v-else type="info" data-testid="search-result-role">关联</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="标识" min-width="200">
            <template #default="{ row }">
              <!-- 关联行缩进（AC-A2 / AC-A8）；命中行不缩进。 -->
              <span
                class="search-results__identifier"
                :class="{
                  'search-results__identifier--related':
                    (row as SearchResultRow).role === 'RELATED',
                }"
              >
                {{ identifierOf(row as SearchResultRow) }}
              </span>
            </template>
          </el-table-column>
          <!-- 命中字段：契约原样字段名标签（本行自身命中字段；HIT 恒非空，
               RELATED 可为空或非空——该行自身也命中时，契约 §4.1）。 -->
          <el-table-column label="命中字段" min-width="200">
            <template #default="{ row }">
              <el-tag
                v-for="field in (row as SearchResultRow).matched_fields"
                :key="field"
                size="small"
                type="success"
                class="search-results__matched"
              >
                {{ field }}
              </el-tag>
            </template>
          </el-table-column>
          <!-- 推导路径：仅关联行（HIT 行 derivation_path == null，不渲染）。 -->
          <el-table-column label="推导路径" min-width="300">
            <template #default="{ row }">
              <span
                v-if="(row as SearchResultRow).role === 'RELATED'"
                class="search-results__path"
                data-testid="search-derivation-path"
              >
                {{ derivationPathText(row as SearchResultRow) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                data-testid="search-result-detail"
                @click="openDetail(row as SearchResultRow)"
              >
                查看
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="search-results__pagination">
          <!-- total = 组织单元（命中项）数（契约 §4），非行数；分页按单元翻页。 -->
          <span class="search-results__unit-count" data-testid="search-unit-count">
            共 {{ total }} 个命中项
          </span>
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            layout="sizes, prev, pager, next"
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </ListStates>
    </section>
  </main>
</template>

<style scoped>
.search-results {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.search-results__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.search-results__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-results__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-results__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
}

.search-results__body {
  margin-top: 16px;
}

/* 关联行：标识缩进 + 浅底色（与命中行可区分，AC-A2 / AC-A8）。 */
.search-results__identifier--related {
  display: inline-block;
  padding-left: 28px;
}

.search-results__table :deep(.el-table__row--related) {
  background-color: var(--el-fill-color-lighter);
}

/* 组织单元之间的分隔线（首单元除外）：单元 = 命中行 + 其关联行。 */
.search-results__table :deep(.el-table__row--group-start .el-table__cell) {
  border-top: 2px solid var(--el-border-color-light);
}

.search-results__pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 16px;
}

.search-results__unit-count {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.search-results__matched {
  margin-right: 4px;
}

.search-results__path {
  color: var(--el-text-color-regular);
  font-size: 13px;
}
</style>
