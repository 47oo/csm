<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { searchClusterResources } from '../api/search'
import type { SearchResultItem, SearchResourceType } from '../api/search'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import ListStates from '../components/ListStates.vue'

/**
 * 搜索结果页（F018 产品页，R-QUERY-005 / AC-D4）。
 *
 * - 调用 GET /api/clusters/{cluster_id}/search（契约 §3，唯一搜索端点）：
 *   **单请求**获得单一混合列表（不分组、不承诺排序，契约 §3「结果顺序」）；
 *   本页不做任何浏览器端拼接 / 关联推导（架构 Handoff 裁定 1）；
 * - 三态互不相同（AC-07）：Loading（骨架屏）/ Empty（200 + items == []，
 *   「无匹配结果」，R-QUERY-004 Empty 语义，不得渲染为错误、不触发全局
 *   会话失效）/ Error（按 error.code 分支渲染，不解析 message：NOT_FOUND →
 *   「未找到资源」，VALIDATION_ERROR → 校验失败，NETWORK_ERROR → 连接失败）；
 * - 每行展示 resource_type 可读标签（六值，与领域类型名一致）+ 资源标识
 *   字段（按类型取 hostname / name / ip_address，契约原样值）+ matched_fields
 *   标签（命中原因，契约原样字段名，不解释 / 不翻译）+「查看」入口；
 * - 「查看」进入对应资源详情（复用 App 既有 open*Detail 导航，携带搜索
 *   视图为返回目标）；返回按钮回集群列表（与无过滤上下文的列表页一致）；
 * - 分页消费契约信封 {items, total, page, page_size}（page_size 选项均在
 *   契约合法区间 [1, 200] 内；参数合法性由服务端校验）。
 */
const props = defineProps<{
  /** 搜索范围：已选定的 Cluster id（R-QUERY-005 前置）。 */
  clusterId: number
  /** 搜索关键字（原样值，不 trim，契约 §2）。 */
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

/** 分页状态；page_size 选项均在契约合法区间 [1, 200] 内。 */
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

/** Empty 判定：请求成功（data 非空）且 items 为空（契约 §3 Empty 语义）。 */
const listEmpty = computed(() => data.value !== null && data.value.items.length === 0)

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
function identifierOf(item: SearchResultItem): string {
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

/** 从结果行进入对应资源详情（复用 App 既有 open*Detail 导航链路）。 */
function openDetail(item: SearchResultItem): void {
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
      <!-- 单一混合列表：不按 resource_type 分组、不承诺排序（契约 §3）。 -->
      <ListStates :loading="isLoading" :error="error" :empty="listEmpty" empty-description="无匹配结果">
        <el-table :data="results" class="search-results__table" data-testid="search-results-table">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              <el-tag>{{ RESOURCE_TYPE_LABELS[row.resource_type as SearchResourceType] }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="标识" min-width="180">
            <template #default="{ row }">
              <span class="search-results__identifier">{{ identifierOf(row as SearchResultItem) }}</span>
            </template>
          </el-table-column>
          <!-- 命中字段：契约原样字段名标签（命中原因，A-4；不解释 / 不翻译）。 -->
          <el-table-column label="命中字段" min-width="240">
            <template #default="{ row }">
              <el-tag
                v-for="field in (row as SearchResultItem).matched_fields"
                :key="field"
                size="small"
                type="success"
                class="search-results__matched"
              >
                {{ field }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                data-testid="search-result-detail"
                @click="openDetail(row as SearchResultItem)"
              >
                查看
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="search-results__pagination">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next"
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

.search-results__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.search-results__matched {
  margin-right: 4px;
}
</style>
