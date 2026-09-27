<script setup lang="ts">
// 资源公共详情页 /clusters/:clusterId/resources/:resourceId（架构 F003 §2.4/§5，需求 §6.3）：
// - 复用 F002/F006 GET /resources/{resource_id}（ResourceFormDetail），不新增只读详情端点；
// - 公共信息：名称、集群、类型、状态（含文字）、状态来源（操作者，BQ-AA）、
//   状态更新时间、更新时间、管理 IP；
// - 网卡/IP：每张网卡只读展示（含网段摘要只读带出）与其 IP 表格；无 IP 网卡正常显示
//   （ips: []，场景 8）；管理 IP 以标识区分（is_management）；
// - 「服务」为占位，由 F007 在同一详情页扩展；类型专有字段（CPU/内存/GPU/SN/宿主等）
//   由 F004 扩展，本页不展示；
// - 任意已登录可读（viewer 只读）；404 资源不存在显式提示；错误不伪装成空详情。
// 集群作用域经 useResourcePageScope 与 URL/store 双向同步（切换集群回到列表）。
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getResource, type ResourceFormDetail } from '../api/resources'
import { apiErrorMessage, isApiError } from '../api/client'
import { formatDateTime } from '../utils/format'
import { resourceStatusLabel, resourceTypeLabel } from '../utils/resourceRules'
import { useResourcePageScope } from '../composables/useResourcePageScope'
import type { ResourceStatus } from '../api/resources'

const route = useRoute()
const router = useRouter()
// 集群作用域同步：URL clusterId ↔ store（详情页直接进入也保持页头选择一致）
useResourcePageScope()

const detail = ref<ResourceFormDetail | null>(null)
const loading = ref(false)
const loadError = ref('')
const notFound = ref(false)

/** 路由参数防御性解析（路由本身以 \d+ 约束 resourceId） */
const resourceId = computed(() => {
  const param = route.params.resourceId
  if (typeof param !== 'string' || !/^\d+$/.test(param)) return null
  return Number(param)
})

async function load(): Promise<void> {
  const id = resourceId.value
  if (id === null) {
    detail.value = null
    loadError.value = '资源 ID 非法'
    return
  }
  loading.value = true
  loadError.value = ''
  notFound.value = false
  try {
    detail.value = await getResource(id)
  } catch (error) {
    // 错误显式呈现，不伪装成空详情；401/403 已由全局处理器提示/跳转
    detail.value = null
    if (isApiError(error) && error.status === 404) {
      notFound.value = true
      loadError.value = '资源不存在或已被删除'
    } else {
      loadError.value = apiErrorMessage(error)
    }
  } finally {
    loading.value = false
  }
}

watch(resourceId, () => void load(), { immediate: true })

/** 返回资源列表（优先使用详情回显的集群；未加载时回退路由参数） */
function backToList(): void {
  const clusterId = detail.value?.cluster_id ?? route.params.clusterId
  if (typeof clusterId !== 'string' && typeof clusterId !== 'number') {
    void router.push({ name: 'clusters' })
    return
  }
  void router.push({ name: 'cluster-resources', params: { clusterId: String(clusterId) } })
}

function statusTagType(status: ResourceStatus): 'success' | 'danger' | 'info' | 'primary' {
  switch (status) {
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
</script>

<template>
  <div class="resource-detail-page">
    <!-- 页头：返回 + 标题 -->
    <div class="resource-detail-head">
      <el-button @click="backToList">返回资源列表</el-button>
      <h2 class="resource-detail-title">资源详情</h2>
    </div>

    <el-card v-if="loading && !detail" shadow="never" class="resource-detail-loading">
      <span class="resource-detail-muted">正在加载资源详情…</span>
    </el-card>

    <el-card v-else-if="loadError" shadow="never">
      <el-empty :description="notFound ? '资源不存在或已被删除' : loadError">
        <el-button v-if="notFound" type="primary" @click="backToList">返回资源列表</el-button>
        <el-button v-else type="primary" @click="load">重试</el-button>
      </el-empty>
    </el-card>

    <template v-else-if="detail">
      <!-- 公共信息（§6.3：名称/集群/类型/状态/状态来源/更新时间/管理 IP） -->
      <el-card shadow="never" class="resource-detail-section">
        <template #header><span class="resource-detail-section-title">公共信息</span></template>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="资源名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="集群">
            {{ detail.cluster_code }} {{ detail.cluster_name }}
          </el-descriptions-item>
          <el-descriptions-item label="类型">
            {{ resourceTypeLabel(detail.resource_type) }}
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)" size="small">
              {{ resourceStatusLabel(detail.status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态来源">
            {{ detail.status_updated_by_username ?? '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="状态更新时间">
            {{ formatDateTime(detail.status_updated_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="更新时间">
            {{ formatDateTime(detail.updated_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="管理 IP">
            <template v-if="detail.management_ip">
              <code class="resource-detail-code">{{ detail.management_ip.address }}</code>
              <span class="resource-detail-muted">（{{ detail.management_ip.interface_name }}）</span>
            </template>
            <span v-else class="resource-detail-muted">—</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 网卡与 IP（§6.3；无 IP 网卡正常显示，场景 8；网段只读摘要） -->
      <el-card shadow="never" class="resource-detail-section">
        <template #header><span class="resource-detail-section-title">网卡与 IP</span></template>
        <el-empty
          v-if="detail.interfaces.length === 0"
          description="该资源尚未登记网卡"
          :image-size="60"
        />
        <div v-else class="resource-detail-nics">
          <div v-for="nic in detail.interfaces" :key="nic.id" class="resource-detail-nic">
            <div class="resource-detail-nic-head">
              <strong class="resource-detail-nic-name">{{ nic.name }}</strong>
              <span v-if="nic.segment" class="resource-detail-nic-segment">
                网段：{{ nic.segment.name }}（{{ nic.segment.cidr }} · {{ nic.segment.purpose }} ·
                {{ nic.segment.technology }}<template v-if="nic.segment.vlan !== null"> · VLAN {{ nic.segment.vlan }}</template>）
              </span>
              <span v-else class="resource-detail-muted">未关联网段</span>
            </div>
            <el-table :data="nic.ips" size="small" class="resource-detail-ip-table">
              <el-table-column label="IP 地址" min-width="150">
                <template #default="{ row }">
                  <code class="resource-detail-code">{{ row.address }}</code>
                </template>
              </el-table-column>
              <el-table-column label="所属网段" min-width="130">
                <template #default="">
                  <template v-if="nic.segment">{{ nic.segment.name }}</template>
                  <span v-else class="resource-detail-muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="管理 IP" width="110">
                <template #default="{ row }">
                  <el-tag v-if="row.is_management" size="small" type="warning">管理 IP</el-tag>
                  <span v-else class="resource-detail-muted">—</span>
                </template>
              </el-table-column>
              <template #empty>
                <span class="resource-detail-muted">该网卡暂无 IP</span>
              </template>
            </el-table>
          </div>
        </div>
      </el-card>

      <!-- 服务（占位：由 F007 在同一详情页扩展） -->
      <el-card shadow="never" class="resource-detail-section">
        <template #header><span class="resource-detail-section-title">服务</span></template>
        <el-empty
          description="该资源关联的服务与部署实例展示将由后续版本提供"
          :image-size="60"
        />
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.resource-detail-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.resource-detail-head {
  display: flex;
  align-items: center;
  gap: 16px;
}
.resource-detail-title {
  margin: 0;
  font-size: 20px;
}
.resource-detail-section-title {
  font-size: 15px;
  font-weight: 600;
}
.resource-detail-section {
  width: 100%;
}
.resource-detail-loading {
  color: #909399;
}
.resource-detail-muted {
  color: #909399;
}
.resource-detail-code {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}
.resource-detail-nics {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.resource-detail-nic-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.resource-detail-nic-name {
  font-size: 14px;
}
.resource-detail-nic-segment {
  color: #606266;
  font-size: 13px;
}
.resource-detail-ip-table {
  width: 100%;
}
</style>
