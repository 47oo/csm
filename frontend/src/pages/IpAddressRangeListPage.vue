<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listClusters } from '../api/clusters'
import type { ClusterRead } from '../api/clusters'
import { ApiError } from '../api/http'
import { listIpAddressRanges } from '../api/ipAddressRanges'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useIpAddressRangeDelete } from '../composables/useIpAddressRangeDelete'
import ListStates from '../components/ListStates.vue'
import IpAddressRangeFormDialog from '../components/IpAddressRangeFormDialog.vue'

/**
 * IP 地址范围段列表页（F020 产品页）。
 *
 * - 调用 GET /api/ip-address-ranges（契约 §3.2），可选 cluster_id 限定
 *   （Cluster 上下文入口：页内集群筛选，与容器页载体筛选同为列表页内能力，
 *   不改其它资源页面）；未筛选时返回全部活跃范围段；
 * - 三态互不相同：Loading / Empty（200 + items 为空；未筛选「暂无 IP 地址
 *   范围段」、按集群筛选「该集群暂无 IP 地址范围段」）/ Error（按 error.code
 *   分支渲染，不解析 message）；
 * - Empty 与 Not Found 可区分（R-QUERY-004）：所筛选的 Cluster 存在但无活跃
 *   范围段 → 200 + items == []（Empty 态）；Cluster 不存在或已逻辑删除 →
 *   404 NOT_FOUND（Error 态渲染「未找到资源」）；
 * - 列展示 start_ip – end_ip（含两端）、cluster_id、名称 / 子网掩码 / VLAN
 *   （F022，R-IP-004：三个可选元数据字段，null 显示占位「—」，与契约
 *   §2 可空语义一致）、更新时间（不透明字符串）；无状态列 / 状态筛选
 *   （Q-002=B）、无 description 列（契约 §2 封闭）；name / subnet_mask /
 *   vlan 不是查询 / 筛选 / 排序参数（契约 §10）：本页不提供按名称 / 掩码 /
 *   VLAN 的筛选或排序入口；
 * - 每行提供详情 / 删除入口；删除二次确认（ElPopconfirm）→ DELETE
 *   /api/ip-address-ranges/{id}（契约 §3.5）。204 / 404 同构刷新；409
 *   CONFLICT + details[].code === 'ACTIVE_CHILDREN_EXIST'（范围内仍有活跃
 *   IP）按 error.code 渲染；401 交由全局会话失效处理；提交中 Loading 且禁
 *   重复提交。删除守卫由后端裁决（§21），前端不预判、不禁用、不隐藏入口；
 * - 登记表单入口（IpAddressRangeFormDialog，POST）：父 Cluster 存在性 /
 *   活跃性（404）、字段合法性（400，含非法掩码 / 越界 VLAN）、同 Cluster
 *   重叠（409 OVERLAP）、同 Cluster 活跃同名（409 DUPLICATE，F022）均由
 *   服务端裁决，前端不预判、不做重叠 / 重名预检；从已筛选集群打开时预选
 *   该集群（可改选）；
 * - 集群筛选选项懒加载：首次展开下拉时 GET /api/clusters（失败可重试），
 *   挂载时只发起一次列表请求；筛选值直接提交，Cluster 存在性由服务端裁决
 *   （非预判）；
 * - 分页参数合法性由服务端校验（400 VALIDATION_ERROR → Error 态渲染）；
 *   本页仅提供合法区间内的固定选项。
 */
const emit = defineEmits<{
  openDetail: [ipAddressRangeId: number]
  back: []
}>()

/** 分页状态；page_size 选项均在契约合法区间 [1, 200] 内。 */
const page = ref(1)
const pageSize = ref(50)

// ---- 集群筛选（页内能力，契约 §3.2 ?cluster_id=） ----

/** 筛选输入（未应用）；null = 未选择。 */
const filterClusterId = ref<number | null>(null)
/** 已应用的集群筛选；null = 全部活跃范围段。查询只依据该状态。 */
const appliedClusterId = ref<number | null>(null)

/** 筛选按钮在未选择集群时禁用（表单未完成；已选择的值直接提交，Cluster
 * 存在性由服务端裁决，非预判）。 */
const filterApplyDisabled = computed(() => filterClusterId.value === null)

function applyFilter(): void {
  if (filterClusterId.value === null) return
  appliedClusterId.value = filterClusterId.value
  page.value = 1
  void run()
}

function clearFilter(): void {
  filterClusterId.value = null
  appliedClusterId.value = null
  page.value = 1
  void run()
}

/** 集群选项（懒加载：首次展开筛选下拉时 listClusters，不在挂载时请求）。 */
const clusterOptions = ref<ClusterRead[]>([])
const clusterOptionsLoading = ref(false)
const clusterOptionsError = ref<ApiError | null>(null)
/** 选项是否已成功加载（失败不置位，下次展开重试）。 */
let clusterOptionsLoaded = false

/** 拉取集群选项。page_size 取契约上限 200（与登记对话框同一取法）。 */
async function loadClusterOptions(): Promise<void> {
  if (clusterOptionsLoaded || clusterOptionsLoading.value) return
  clusterOptionsLoading.value = true
  clusterOptionsError.value = null
  try {
    const data = await listClusters({ page: 1, page_size: 200 })
    clusterOptions.value = data.items
    clusterOptionsLoaded = true
  } catch (err) {
    clusterOptions.value = []
    clusterOptionsError.value =
      err instanceof ApiError
        ? err
        : new ApiError({ status: 0, code: 'UNKNOWN_ERROR', message: '发生未知错误。' })
  } finally {
    clusterOptionsLoading.value = false
  }
}

/** 首次展开筛选下拉时懒加载选项（挂载时只发起一次列表请求）。 */
function handleFilterClusterVisible(visible: boolean): void {
  if (visible) void loadClusterOptions()
}

const {
  data: rangeData,
  loading,
  error,
  run,
} = useAsyncQuery(() =>
  listIpAddressRanges({
    page: page.value,
    page_size: pageSize.value,
    cluster_id: appliedClusterId.value ?? undefined,
  }),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useIpAddressRangeDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 刷新列表。
  onRemoved: () => run(),
})

const ranges = computed(() => rangeData.value?.items ?? [])

/**
 * Loading 判定：请求进行中，或首次请求尚未返回（data 与 error 均为空）。
 * 后者避免首帧闪现空内容。
 */
const isLoading = computed(
  () => loading.value || (rangeData.value === null && error.value === null),
)

/** Empty 判定：请求成功（data 非空）且 items 为空（api-conventions.md §7）。 */
const listEmpty = computed(
  () => rangeData.value !== null && rangeData.value.items.length === 0,
)

const total = computed(() => rangeData.value?.total ?? 0)

/** 过滤上下文文案：Empty 态与标题下的过滤标签随集群筛选区分。 */
const clusterFilterLabel = computed(() =>
  appliedClusterId.value !== null ? `集群 #${appliedClusterId.value}` : null,
)
const emptyDescription = computed(() =>
  appliedClusterId.value !== null ? '该集群暂无 IP 地址范围段' : '暂无 IP 地址范围段',
)

onMounted(() => {
  void run()
})

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

function openDetail(ipAddressRangeId: number): void {
  emit('openDetail', ipAddressRangeId)
}

function goBack(): void {
  emit('back')
}

/** 二次确认通过后删除该行范围段；状态管理与错误渲染见 useIpAddressRangeDelete。 */
function confirmDelete(ipAddressRangeId: number): void {
  void requestDelete(ipAddressRangeId)
}

// ---- 登记入口（POST /api/ip-address-ranges） ----

const createDialogVisible = ref(false)

function handleCreated(): void {
  // 登记成功 → 刷新列表（新记录按 id 升序可能位于其他页，刷新当前页即可）。
  void run()
}
</script>

<template>
  <main
    class="range-list"
    :data-cluster-filter="appliedClusterId ?? 'none'"
  >
    <header class="range-list__header">
      <div class="range-list__nav">
        <el-button @click="goBack">返回集群列表</el-button>
        <h1 class="range-list__title">
          IP 地址范围段列表
          <el-tag v-if="clusterFilterLabel !== null" class="range-list__filter">
            {{ clusterFilterLabel }}
          </el-tag>
        </h1>
      </div>
      <div class="range-list__actions">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
        <el-button type="primary" data-testid="open-create-dialog" @click="createDialogVisible = true">
          登记 IP 地址范围段
        </el-button>
      </div>
    </header>

    <!-- 集群筛选（契约 §3.2 ?cluster_id=；选项懒加载，Cluster 存在性由服务端
         裁决 → Empty / Not Found 两态可区分）。 -->
    <section class="range-list__filter-bar">
      <el-select
        v-model="filterClusterId"
        class="range-list__filter-cluster"
        placeholder="按集群筛选（全部）"
        data-testid="range-filter-cluster"
        :loading="clusterOptionsLoading"
        @visible-change="handleFilterClusterVisible"
      >
        <el-option
          v-for="cluster in clusterOptions"
          :key="cluster.id"
          :label="`${cluster.name}（ID ${cluster.id}）`"
          :value="cluster.id"
        />
      </el-select>
      <div v-if="clusterOptionsError !== null" class="range-list__filter-hint">
        集群选项加载失败（{{ clusterOptionsError.code }}）。
        <el-button link type="primary" @click="loadClusterOptions">重试</el-button>
      </div>
      <el-button
        type="primary"
        plain
        data-testid="range-filter-apply"
        :disabled="filterApplyDisabled"
        @click="applyFilter"
      >
        筛选
      </el-button>
      <el-button data-testid="range-filter-clear" @click="clearFilter">重置</el-button>
    </section>

    <section class="range-list__body">
      <ListStates
        :loading="isLoading"
        :error="error"
        :empty="listEmpty"
        :empty-description="emptyDescription"
      >
        <!-- 删除失败提示（409 等）：仅在内容态与表格同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="range-list__delete-error"
          :data-delete-error-code="deleteErrorView.code"
        >
          <el-alert
            type="error"
            :title="deleteErrorView.title"
            :description="deleteErrorView.description"
            show-icon
            closable
            @close="clearDeleteError"
          />
        </div>

        <!-- 列集合封闭：id / cluster_id / start_ip – end_ip / name /
             subnet_mask / vlan（F022，null → 「—」占位）/ updated_at；无状态列
             （Q-002=B）、无 description 列（契约 §2）。三字段不是筛选 / 排序
             参数（契约 §10），不提供对应入口。 -->
        <el-table :data="ranges" class="range-list__table">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="cluster_id" label="所属集群 ID" width="140" />
          <!-- start_ip / end_ip 均为服务端规范化后的契约原样值，不做任何变换
               （契约 §2 / §7）。 -->
          <el-table-column label="地址范围（start – end，含两端）" min-width="240">
            <template #default="{ row }">{{ row.start_ip }} – {{ row.end_ip }}</template>
          </el-table-column>
          <!-- F022 三个可选元数据字段：契约原样值，null → 「—」占位（未登记），
               不做任何变换 / 推导。 -->
          <el-table-column label="名称" min-width="120">
            <template #default="{ row }">{{ row.name ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="子网掩码" min-width="140">
            <template #default="{ row }">{{ row.subnet_mask ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="VLAN" width="90">
            <template #default="{ row }">{{ row.vlan ?? '—' }}</template>
          </el-table-column>
          <el-table-column prop="updated_at" label="更新时间" min-width="200" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
              <!-- 删除入口：对所有行开放；删除守卫由后端裁决（§21），
                   前端不预判（不禁用、不隐藏任何行的删除入口）。 -->
              <el-popconfirm
                title="确定删除该 IP 地址范围段吗？删除后不可恢复。"
                confirm-button-text="删除"
                cancel-button-text="取消"
                confirm-button-type="danger"
                :width="200"
                @confirm="confirmDelete(row.id)"
              >
                <template #reference>
                  <el-button
                    link
                    type="danger"
                    :loading="deletingId === row.id"
                    :disabled="deletingId !== null"
                  >
                    删除
                  </el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <div class="range-list__pagination">
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

    <!-- 登记表单（POST）：父 Cluster 存在性 / 字段合法性 / 同 Cluster 重叠
         均由服务端裁决；从已筛选集群打开时预选该集群。 -->
    <IpAddressRangeFormDialog
      v-model="createDialogVisible"
      mode="create"
      :preset-cluster-id="appliedClusterId"
      @success="handleCreated"
    />
  </main>
</template>

<style scoped>
.range-list {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.range-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.range-list__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.range-list__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.range-list__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 20px;
}

.range-list__filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.range-list__filter-cluster {
  width: 240px;
}

.range-list__filter-hint {
  color: #f56c6c;
  font-size: 12px;
}

.range-list__body {
  margin-top: 16px;
}

.range-list__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.range-list__delete-error {
  margin-bottom: 16px;
}
</style>
