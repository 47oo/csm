<script setup lang="ts">
// 计算资源统一列表页 /clusters/:clusterId/resources（架构 F003 §2.4/§7，需求 §6.2）：
// - 首屏确认集群（复用 useClusterStore；未选择要求选择，不隐式切换作用域，BQ-H/场景 56）；
// - 全部/裸金属/虚拟机切换（= resource_type 筛选）、状态筛选、名称/IP 搜索（限当前集群并
//   显式展示作用域，响应回显 scope）、服务端分页、默认按名称排序；
// - 状态含文字（含颜色标签，不只靠颜色，§9.4）；窄屏表格横向滚动（§9.4）；
// - Loading / Empty / Error 状态显式区分：错误不伪装成空列表；
// - 普通列表仅显示仍存对象（真实删除即删行，无软删）；列表只读，无写操作。
// 前端权限仅隐藏「新增资源」入口（viewer 只读），服务端为最终校验。
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  RESOURCE_STATUS_OPTIONS,
  RESOURCE_TYPE_OPTIONS,
  canManageResources,
} from '../utils/resourceRules'
import { formatDateTime } from '../utils/format'
import { useAuthStore } from '../stores/auth'
import { useResourcePageScope } from '../composables/useResourcePageScope'
import { useResourceList } from '../composables/useResourceList'
import type { ResourceListItem, ResourceStatus } from '../api/resources'

const router = useRouter()
const auth = useAuthStore()
const { scopeClusterId, scopeCluster } = useResourcePageScope()

// 写操作入口可见性（服务端为最终校验）：新增资源仅 maintainer/admin；viewer 只读
const canManage = computed(() => canManageResources(auth.user?.role))

const {
  items,
  total,
  page,
  pageSize,
  q,
  resourceType,
  status,
  sort,
  scope,
  loading,
  loadError,
  setQ,
  searchNow,
  setType,
  setStatus,
  setSort,
  setPage,
  setPageSize,
  resetFilters,
  retry,
} = useResourceList(scopeClusterId)

/** 显式作用域展示（§6.2「搜索 IP 时显示当前集群作用域」）：优先使用集群选择缓存
 * （与 URL 同步、始终新鲜）；未加载时回退最近一次响应回显的 ClusterScope
 * （Contract F003 §1），均不可用时回退集群 ID */
const scopeText = computed(() => {
  if (scopeCluster.value) return `${scopeCluster.value.code} ${scopeCluster.value.name}`
  if (scope.value) return `${scope.value.cluster_code} ${scope.value.cluster_name}`
  return `#${scopeClusterId.value}`
})

const hasFilter = computed(
  () => q.value.trim() !== '' || resourceType.value !== '' || status.value !== '',
)

const emptyDescription = computed(() =>
  hasFilter.value ? '未找到匹配的计算资源' : '该集群暂无计算资源',
)

/** 状态标签颜色（§9.4：颜色为辅助，文字必需；文字用服务端返回的 status_label） */
function statusTagType(value: ResourceStatus): 'success' | 'danger' | 'info' | 'primary' {
  switch (value) {
    case 'IDLE':
      return 'success'
    case 'DOWN':
      return 'danger'
    case 'UNKNOWN':
      return 'info'
    default:
      return 'primary'
  }
}

function goDetail(row: ResourceListItem): void {
  void router.push({
    name: 'resource-detail',
    params: { clusterId: String(row.cluster_id), resourceId: String(row.id) },
  })
}

function goCreate(): void {
  if (scopeClusterId.value === null) return
  void router.push({
    name: 'resource-new',
    params: { clusterId: String(scopeClusterId.value) },
  })
}
</script>

<template>
  <div class="resources-page">
    <!-- 无选中集群：提示选择（首屏必须选择或确认集群；不隐式切换作用域） -->
    <el-card v-if="scopeClusterId === null" shadow="never">
      <el-empty description="尚未选择集群：计算资源按集群登记与展示，请先在页头选择集群作用域">
        <el-button type="primary" @click="router.push({ name: 'clusters' })">前往集群列表</el-button>
      </el-empty>
    </el-card>

    <template v-else>
      <!-- 集群作用域标题 -->
      <div class="resources-scope">
        <h2 class="resources-title">计算资源</h2>
        <span class="resources-cluster">
          当前集群：
          <strong>{{ scopeText }}</strong>
          <span class="resources-cluster-hint">（可在页头切换集群，切换后列表刷新；搜索仅限本集群，不隐式切换作用域）</span>
        </span>
      </div>

      <!-- 筛选/搜索区 -->
      <el-card class="resources-filter" shadow="never">
        <el-form inline @submit.prevent="searchNow">
          <el-form-item label="类型">
            <el-radio-group :model-value="resourceType" @change="setType">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button
                v-for="opt in RESOURCE_TYPE_OPTIONS"
                :key="opt.value"
                :value="opt.value"
              >
                {{ opt.label }}
              </el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="状态">
            <el-select :model-value="status" style="width: 150px" @change="setStatus">
              <el-option value="" label="全部状态" />
              <el-option
                v-for="opt in RESOURCE_STATUS_OPTIONS"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="排序">
            <el-select :model-value="sort" style="width: 150px" @change="setSort">
              <el-option value="name" label="名称 升序" />
              <el-option value="-name" label="名称 降序" />
              <el-option value="updated_at" label="更新时间 升序" />
              <el-option value="-updated_at" label="更新时间 降序" />
              <el-option value="created_at" label="创建时间 升序" />
              <el-option value="-created_at" label="创建时间 降序" />
              <el-option value="status" label="状态 升序" />
              <el-option value="-status" label="状态 降序" />
            </el-select>
          </el-form-item>
          <el-form-item label="搜索">
            <div class="resources-search">
              <el-input
                :model-value="q"
                placeholder="资源名称 / 资源 ID / IPv4（部分匹配）"
                clearable
                style="width: 260px"
                @update:model-value="setQ"
                @keyup.enter="searchNow"
                @clear="searchNow"
              />
              <!-- 显式作用域展示（§6.2）：搜索限定当前集群 -->
              <span class="resources-search-scope" data-test-id="resource-search-scope">
                当前集群：{{ scopeText }}（IP 搜索仅限本集群）
              </span>
            </div>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="searchNow">查询</el-button>
            <el-button @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 列表区 -->
      <el-card shadow="never">
        <div class="resources-toolbar">
          <h3 class="resources-list-title">资源列表</h3>
          <!-- 新增资源仅 maintainer/admin（写入口归 F002 表单；服务端校验为最终保证） -->
          <el-button v-if="canManage" type="primary" @click="goCreate">新增资源</el-button>
        </div>

        <el-alert
          v-if="loadError"
          type="error"
          :closable="false"
          show-icon
          :title="loadError"
          class="resources-error"
        >
          <el-button size="small" @click="retry">重试</el-button>
        </el-alert>

        <el-table v-else v-loading="loading" :data="items" class="resources-table">
          <el-table-column label="资源名称" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <el-button link type="primary" @click="goDetail(row)">{{ row.name }}</el-button>
            </template>
          </el-table-column>
          <el-table-column label="集群" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.cluster_code }} {{ row.cluster_name }}</template>
          </el-table-column>
          <el-table-column label="类型" min-width="100">
            <template #default="{ row }">{{ row.resource_type_label }}</template>
          </el-table-column>
          <el-table-column label="状态" min-width="110">
            <template #default="{ row }">
              <!-- 状态含文字（服务端 status_label），颜色仅辅助（§9.4） -->
              <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_label }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="管理 IP" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <template v-if="row.management_ip">
                <code class="resources-code">{{ row.management_ip.address }}</code>
                <span class="resources-muted">（{{ row.management_ip.interface_name }}）</span>
              </template>
              <span v-else class="resources-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" min-width="170">
            <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
          </el-table-column>
          <template #empty>
            <el-empty :description="emptyDescription" />
          </template>
        </el-table>

        <div class="resources-pagination">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :total="total"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="setPage"
            @size-change="setPageSize"
          />
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.resources-page {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.resources-scope {
  display: flex;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
}
.resources-title {
  margin: 0;
  font-size: 20px;
}
.resources-cluster {
  color: #606266;
}
.resources-cluster-hint {
  color: #909399;
  font-size: 12px;
}
.resources-search {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.resources-search-scope {
  color: #909399;
  font-size: 12px;
  white-space: nowrap;
}
.resources-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.resources-list-title {
  margin: 0;
  font-size: 16px;
}
.resources-error {
  margin-bottom: 12px;
}
/* 窄屏表格横向滚动（§9.4）：列设 min-width，el-table 容器自动出现横向滚动条 */
.resources-table {
  width: 100%;
}
.resources-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.resources-code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}
.resources-muted {
  color: #909399;
}
</style>
