<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getIpAddressRange } from '../api/ipAddressRanges'
import type { IpAddressRangeRead } from '../api/ipAddressRanges'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useIpAddressRangeDelete } from '../composables/useIpAddressRangeDelete'
import ErrorState from '../components/ErrorState.vue'
import IpAddressRangeFormDialog from '../components/IpAddressRangeFormDialog.vue'

/**
 * IP 地址范围段详情页（F020 产品页）。
 *
 * - 调用 GET /api/ip-address-ranges/{id}（契约 §3.3，规范路径），展示全部
 *   6 字段（契约 §2 封闭集合）：id / cluster_id / start_ip / end_ip /
 *   created_at / updated_at；时间为不透明字符串原样展示；start_ip / end_ip
 *   为服务端规范化值原样展示；无状态字段展示 / 编辑（Q-002=B，范围段无
 *   状态）；无 name / description 展示（契约 §2 封闭）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同
 *   状态（R-QUERY-004）；
 * - start_ip / end_ip 修正入口（IpAddressRangeFormDialog，PATCH 契约 §3.4）：
 *   **仅此两个字段可编辑**；cluster_id 登记后不可变（契约 §3.4），只读展示，
 *   不提供编辑输入；修正后由服务端重新执行 IPv4 解析 / start<=end / 重叠
 *   校验（409 OVERLAP / 400 / 404 按 error.code 渲染，不解析 message），
 *   前端不重复实现业务守卫（§21）；
 * - 删除入口（ElPopconfirm）→ DELETE /api/ip-address-ranges/{id}（契约
 *   §3.5）。删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取 →
 *   404 → 既有独立 Not Found 态；409 CONFLICT + details[].code ===
 *   'ACTIVE_CHILDREN_EXIST'（范围内仍有活跃 IP）按 error.code 渲染冲突
 *   提示；401 交由全局会话失效处理；提交中 Loading 且禁重复提交。删除守卫
 *   由后端裁决（§21）；
 * - 修改 / 删除失败均按 error.code 分支渲染，不解析 message。
 */
const props = defineProps<{ ipAddressRangeId: number }>()

const emit = defineEmits<{ back: [] }>()

const { data, loading, error, run } = useAsyncQuery(() =>
  getIpAddressRange(props.ipAddressRangeId),
)

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useIpAddressRangeDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取：
  // 服务端按契约对已删资源返回 404 → 进入既有独立 Not Found 态。
  onRemoved: () => run(),
})

onMounted(() => {
  void run()
})

interface DetailItem {
  key: string
  label: string
  /** 展示值：契约原样值，不做任何变换。 */
  value: string
}

/** 详情字段（顺序即展示顺序）；值为契约原样值，不做任何变换。 */
const detailItems = computed<DetailItem[]>(() => {
  const range: IpAddressRangeRead | null = data.value
  if (range === null) return []
  return [
    { key: 'id', label: 'ID', value: String(range.id) },
    { key: 'cluster_id', label: '所属集群 ID', value: String(range.cluster_id) },
    { key: 'start_ip', label: '起始 IP', value: range.start_ip },
    { key: 'end_ip', label: '结束 IP', value: range.end_ip },
    { key: 'created_at', label: '登记时间', value: range.created_at },
    { key: 'updated_at', label: '更新时间', value: range.updated_at },
  ]
})

/**
 * 展示状态：
 * - not-found 是独立的 404 态（「资源不存在或已被删除」），
 *   与列表 Empty、其他 Error 均可区分（R-QUERY-004）；
 * - 首次请求尚未返回（data 与 error 均为空）按 Loading 处理，避免闪现空内容。
 */
const state = computed<'loading' | 'not-found' | 'error' | 'content'>(() => {
  if (loading.value) return 'loading'
  if (error.value !== null) {
    return error.value.code === 'NOT_FOUND' ? 'not-found' : 'error'
  }
  return data.value !== null ? 'content' : 'loading'
})

function backToList(): void {
  emit('back')
}

/** 二次确认通过后删除当前范围段；状态管理与错误渲染见 useIpAddressRangeDelete。 */
function confirmDelete(): void {
  void requestDelete(props.ipAddressRangeId)
}

// ---- start_ip / end_ip 修正入口（PATCH） ----

const editDialogVisible = ref(false)

function handleUpdated(): void {
  // 保存成功 → 重新读取详情（data 更新为服务端返回的最新值）。
  void run()
}
</script>

<template>
  <main class="range-detail" :data-state="state">
    <header class="range-detail__header">
      <div class="range-detail__nav">
        <el-button @click="backToList">返回列表</el-button>
        <h1 class="range-detail__title">IP 地址范围段详情</h1>
      </div>
      <!-- start_ip / end_ip 修正入口与删除入口：仅内容态出现；cluster_id
           不可变（契约 §3.4），只读展示、不提供编辑；删除守卫由后端 409
           裁决（§21），前端不预判。 -->
      <div v-if="state === 'content'" class="range-detail__actions">
        <el-button type="primary" plain data-testid="open-edit-dialog" @click="editDialogVisible = true">
          编辑
        </el-button>
        <el-popconfirm
          title="确定删除该 IP 地址范围段吗？删除后不可恢复。"
          confirm-button-text="删除"
          cancel-button-text="取消"
          confirm-button-type="danger"
          :width="200"
          @confirm="confirmDelete"
        >
          <template #reference>
            <el-button type="danger" plain :loading="deletingId !== null">删除</el-button>
          </template>
        </el-popconfirm>
      </div>
    </header>

    <section class="range-detail__body">
      <div v-if="state === 'loading'" class="range-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <template v-else>
        <!-- 删除失败提示（409 等）：与详情内容同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="range-detail__delete-error"
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
        <el-descriptions :column="1" border>
          <el-descriptions-item
            v-for="item in detailItems"
            :key="item.key"
            :label="item.label"
          >
            {{ item.value }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </section>

    <!-- 编辑表单（PATCH）：仅 start_ip / end_ip；cluster_id / id / created_at
         不在其中（不可变，契约 §3.4）。 -->
    <IpAddressRangeFormDialog
      v-model="editDialogVisible"
      mode="edit"
      :ip-address-range="data"
      @success="handleUpdated"
    />
  </main>
</template>

<style scoped>
.range-detail {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.range-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.range-detail__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.range-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.range-detail__title {
  margin: 0;
  font-size: 20px;
}

.range-detail__body {
  margin-top: 16px;
}

.range-detail__loading {
  padding: 8px 0;
}

.range-detail__delete-error {
  margin-bottom: 16px;
}
</style>
