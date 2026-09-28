<script setup lang="ts">
// 计算资源表单页（架构 F002 §2.4 + F006 §2.4）：
// - 路由 /clusters/:clusterId/resources/new（新增）与 /clusters/:clusterId/resources/:resourceId/edit（编辑）；
// - 新增：集群可选（复用 F001 useClusterStore；切换清除不再匹配的网段选择 §7.1）、
//   资源类型必选（创建后只读）、状态、网卡卡片；一次提交公共信息 + 全部网卡 + 全部 IP +
//   管理 IP（§4.5 整单原子）；
// - 每张网卡 IP 区：手动输入 / 自动分配（未选网段禁用并提示先选网段，§4.6.7/场景 31；
//   自动分配仅网段已启用自动范围时可用，服务端权威）；IP 列表展示与删除（既有 IP 标记
//   「将删除」可恢复，提交映射 op:'delete'；未列出=未修改；不可改地址）；
// - 管理 IP：资源级选择，候选为本表单将保存的 IP（§4.2.9）；删除当前管理 IP/其网卡时
//   强制显式清空/重选（§4.2.11/场景 46）；
// - 同名 409 RESOURCE_NAME_EXISTS → existing_resource_id 弹确认进入编辑（§4.1.10）；
// - 删除：二次确认须输入资源名称（BQ-Z）；RESOURCE_HAS_INTERFACES 引导先删网卡；
// - 409 冲突（VERSION_CONFLICT / IP_ALREADY_IN_USE 等）保留输入不关窗；字段级错误定位到
//   具体字段、网卡卡片与 IP 条目（interfaces[i].ips[j]，§7.3）。
// 状态与提交逻辑见 composables/useResourceForm；权限仅隐藏入口，服务端为最终校验（§7.2）。
import { useResourceForm, MANAGEMENT_IP_KEEP, MANAGEMENT_IP_NONE } from '../composables/useResourceForm'
import type { InterfaceCard } from '../utils/resourceRules'
import {
  RESOURCE_STATUS_OPTIONS,
  RESOURCE_TYPE_OPTIONS,
  resourceTypeLabel,
} from '../utils/resourceRules'
import { formatDateTime } from '../utils/format'
import EnumSelect from '../components/EnumSelect.vue'
import type { ResourceStatus, ResourceType } from '../api/resources'
import { useRouter } from 'vue-router'

const router = useRouter()

const {
  mode,
  canManage,
  loading,
  loadError,
  notFound,
  name,
  resourceType,
  status,
  cards,
  detail,
  selectedClusterId,
  segmentOptions,
  segmentsLoading,
  segmentsError,
  submitting,
  conflict,
  conflictResolved,
  refreshingVersion,
  formNotice,
  fieldErrors,
  sameNamePrompt,
  deleteVisible,
  deleteConfirmInput,
  deleteSubmitting,
  deleteConfirmError,
  deleteBlockError,
  deleteVersionConflict,
  deleteConfirmMatched,
  remainingInterfaceCount,
  managementIpCandidates,
  managementIpValue,
  managementKeepLabel,
  clusterOptions,
  clusterLoadError,
  init,
  retryLoadClusters,
  retryLoadSegments,
  selectCluster,
  addInterface,
  removeInterface,
  restoreInterface,
  setCardSegment,
  clearCardError,
  segmentSummary,
  addCardIp,
  removeCardIp,
  restoreCardIp,
  clearCardIpError,
  setManagementIpValue,
  isCurrentManagementIp,
  submit,
  dismissSameName,
  confirmSameNameGoEdit,
  refreshVersionKeepInput,
  openDelete,
  closeDelete,
  submitDelete,
} = useResourceForm()

/** 新增模式集群选择（el-select 清空归一为 null） */
function handleClusterChange(id: unknown): void {
  void selectCluster(typeof id === 'number' ? id : null)
}

/** 资源类型选择（EnumSelect 清空归一为 null；必选字段，实际不可清空；'' = 未选） */
function handleTypeChange(value: ResourceType | '' | null): void {
  resourceType.value = value ?? ''
  fieldErrors.resource_type = ''
}

/** 状态选择（EnumSelect 清空归一为 null；不可清空，仅类型层面兼容） */
function handleStatusChange(value: ResourceStatus | null): void {
  status.value = value ?? 'ALLOC'
  fieldErrors.status = ''
}

/** 网卡网段选择（清空归一为 null = 暂不选网段） */
function handleSegmentChange(card: InterfaceCard, id: unknown): void {
  setCardSegment(card, typeof id === 'number' ? id : null)
}

/** 同名确认对话框关闭（非确认路径 = 留在本页，输入保留） */
function handleSameNameDialog(visible: unknown): void {
  if (visible !== true) dismissSameName()
}

function handleDeleteDialog(visible: unknown): void {
  if (visible !== true) closeDelete()
}

function handleConflictResolvedClose(): void {
  conflictResolved.value = false
}
</script>

<template>
  <div class="resource-form-page">
    <!-- 加载中 -->
    <el-card v-if="loading" shadow="never" class="resource-loading" />

    <!-- 编辑：资源不存在 / 已被删除 -->
    <el-card v-else-if="notFound" shadow="never">
      <el-empty description="该资源不存在或已被删除（历史记录仍保留，由管理员查询）">
        <el-button type="primary" @click="router.push({ name: 'clusters' })">返回集群列表</el-button>
      </el-empty>
    </el-card>

    <!-- 加载失败（可重试） -->
    <el-card v-else-if="loadError" shadow="never">
      <el-alert type="error" :closable="false" show-icon :title="loadError" />
      <el-button class="resource-retry" @click="init">重试</el-button>
    </el-card>

    <template v-else>
      <!-- 标题与作用域 -->
      <div class="resource-form-header">
        <h2 class="resource-form-title">{{ mode === 'create' ? '新增计算资源' : '编辑计算资源' }}</h2>
        <span v-if="detail" class="resource-form-scope">
          集群：<strong>{{ detail.cluster_code }} {{ detail.cluster_name }}</strong>
          <span class="resource-form-scope-hint">（所属集群创建后不可修改）</span>
        </span>
        <el-tag v-if="!canManage" type="info">只读（运维查看者）</el-tag>
      </div>

      <!-- 查看者提示：权限由服务端最终校验，前端仅隐藏写入口 -->
      <el-alert
        v-if="!canManage"
        type="info"
        :closable="false"
        show-icon
        title="当前角色为只读：可查看资源信息；新增 / 编辑 / 删除由资源维护者与平台管理员执行"
        class="resource-readonly-notice"
      />

      <el-form label-position="top" @submit.prevent="submit">
        <!-- 公共信息 -->
        <el-card shadow="never" class="resource-section">
          <template #header><span class="resource-section-title">公共信息</span></template>

          <!-- 新增：集群选择；编辑：只读回显 -->
          <el-form-item
            v-if="mode === 'create'"
            label="所属集群"
            :error="fieldErrors.cluster_id || undefined"
          >
            <el-select
              :model-value="selectedClusterId"
              filterable
              placeholder="选择集群（本次新增归属该集群，创建后不可修改）"
              class="resource-cluster-select"
              :disabled="!canManage"
              @change="handleClusterChange"
            >
              <el-option
                v-for="c in clusterOptions"
                :key="c.id"
                :value="c.id"
                :label="`${c.code} ${c.name}`"
              />
            </el-select>
            <div v-if="clusterLoadError" class="resource-inline-error">
              集群列表加载失败：{{ clusterLoadError }}
              <el-button link type="primary" size="small" @click="retryLoadClusters">重试</el-button>
            </div>
          </el-form-item>
          <el-form-item v-else label="所属集群（创建后不可修改）">
            <el-input :model-value="detail ? `${detail.cluster_code} ${detail.cluster_name}` : ''" disabled />
          </el-form-item>

          <div class="resource-field-row">
            <el-form-item label="资源名称（主机名）" class="resource-field-grow" :error="fieldErrors.name || undefined">
              <el-input
                v-model="name"
                placeholder="同集群内唯一（去首尾空格、区分大小写；裸金属与虚拟机统一判重）"
                :disabled="!canManage"
                @input="fieldErrors.name = ''"
              />
            </el-form-item>
          </div>

          <div class="resource-field-row">
            <!-- 新增：类型必选（创建后不可修改）；编辑：只读回显 -->
            <el-form-item
              v-if="mode === 'create'"
              label="资源类型"
              class="resource-field-grow"
              :error="fieldErrors.resource_type || undefined"
            >
              <!-- 固定枚举下拉（F008）：中文展示名/英文代码均可输入匹配 -->
              <EnumSelect
                :model-value="resourceType"
                :options="RESOURCE_TYPE_OPTIONS"
                placeholder="裸金属 / 虚拟机（创建后不可修改）"
                class="resource-type-select"
                :disabled="!canManage"
                @update:model-value="handleTypeChange"
              />
            </el-form-item>
            <el-form-item v-else label="资源类型（创建后不可修改）" class="resource-field-grow">
              <el-input :model-value="resourceTypeLabel(resourceType)" disabled />
            </el-form-item>

            <el-form-item label="状态" class="resource-field-grow" :error="fieldErrors.status || undefined">
              <!-- 固定枚举下拉（F008）：中文展示名/英文代码均可输入匹配 -->
              <EnumSelect
                :model-value="status"
                :options="RESOURCE_STATUS_OPTIONS"
                class="resource-status-select"
                :disabled="!canManage"
                @update:model-value="handleStatusChange"
              />
            </el-form-item>
          </div>

          <!-- 编辑：状态来源与状态更新时间（§4.3/BQ-AA：仅记录操作者与单一状态时间） -->
          <el-descriptions
            v-if="mode === 'edit' && detail"
            :column="2"
            size="small"
            border
            class="resource-status-info"
          >
            <el-descriptions-item label="状态来源">
              {{ detail.status_updated_by_username ?? '—' }}
            </el-descriptions-item>
            <el-descriptions-item label="状态更新时间">
              {{ formatDateTime(detail.status_updated_at) }}
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- 网卡卡片 -->
        <el-card shadow="never" class="resource-section">
          <template #header>
            <div class="resource-nics-head">
              <span class="resource-section-title">
                网卡
                <span class="resource-nics-hint">
                  （同一资源下 0..N 张；接口名唯一；每张可选 0..1 个本集群网段；每张可分配 0..N 个 IP）
                </span>
              </span>
              <span v-if="segmentsLoading" class="resource-nics-loading">网段加载中…</span>
              <el-button v-if="canManage" type="primary" plain @click="addInterface">添加网卡</el-button>
            </div>
          </template>

          <el-alert
            v-if="segmentsError"
            type="error"
            :closable="false"
            show-icon
            :title="`网段列表加载失败：${segmentsError}`"
            class="resource-segments-error"
          >
            <el-button size="small" @click="retryLoadSegments">重试</el-button>
          </el-alert>

          <el-empty
            v-if="cards.length === 0"
            description="暂无网卡：可先保存资源，稍后通过同一表单补充（一次提交整单原子）"
            :image-size="70"
          />

          <el-card
            v-for="(card, index) in cards"
            :key="card.key"
            shadow="never"
            class="nic-card"
            :class="{ 'nic-card-removed': card.removed }"
          >
            <div class="nic-card-head">
              <span class="nic-card-title">
                第 {{ index + 1 }} 张网卡
                <el-tag v-if="card.id === null" size="small" type="success">新增</el-tag>
                <el-tag v-if="card.removed" size="small" type="danger">将删除</el-tag>
              </span>
              <span v-if="canManage">
                <el-button v-if="!card.removed" link type="danger" @click="removeInterface(card.key)">
                  删除网卡
                </el-button>
                <el-button v-else link type="primary" @click="restoreInterface(card.key)">恢复</el-button>
              </span>
            </div>

            <div class="nic-card-body" :class="{ 'nic-card-body-removed': card.removed }">
              <div class="resource-field-row">
                <el-form-item label="接口名" class="resource-field-grow" :error="fieldErrors.cards[card.key]?.name || undefined">
                  <el-input
                    v-model="card.name"
                    placeholder="如 eth0 / ib0；同一资源下唯一（去首尾空格、区分大小写）"
                    :disabled="!canManage || card.removed"
                    @input="clearCardError(card.key, 'name')"
                  />
                </el-form-item>
                <el-form-item
                  label="网络范围（网段，可暂不选）"
                  class="resource-field-grow"
                  :error="fieldErrors.cards[card.key]?.segment_id || undefined"
                >
                  <el-select
                    :model-value="card.segmentId"
                    clearable
                    filterable
                    placeholder="选择本集群网段（分配 IP 前必须选定）"
                    class="resource-segment-select"
                    :disabled="!canManage || card.removed || segmentsLoading"
                    @change="handleSegmentChange(card, $event)"
                  >
                    <el-option
                      v-for="s in segmentOptions"
                      :key="s.id"
                      :value="s.id"
                      :label="`${s.name} · ${s.cidr} · ${s.purpose}`"
                    />
                  </el-select>
                </el-form-item>
              </div>

              <!-- 选定网段后只读带出（§4.2.7/§7.1；不单独录入 technology/purpose，场景 29） -->
              <el-descriptions
                v-if="segmentSummary(card.segmentId)"
                :column="5"
                size="small"
                border
                class="nic-segment-info"
              >
                <el-descriptions-item label="技术类型">
                  {{ segmentSummary(card.segmentId)?.technology }}
                </el-descriptions-item>
                <el-descriptions-item label="用途">
                  {{ segmentSummary(card.segmentId)?.purpose }}
                </el-descriptions-item>
                <el-descriptions-item label="前缀（CIDR）">
                  {{ segmentSummary(card.segmentId)?.cidr }}
                </el-descriptions-item>
                <el-descriptions-item label="VLAN">
                  {{ segmentSummary(card.segmentId)?.vlan ?? '—' }}
                </el-descriptions-item>
                <el-descriptions-item label="网关">
                  {{ segmentSummary(card.segmentId)?.gateway ?? '未设置' }}
                </el-descriptions-item>
              </el-descriptions>

              <!-- IP 分配区（F006 §2.4）：手动输入 / 自动分配；未选网段禁用并提示先选网段（§4.6.7、场景 31）；
                   自动分配仅网段已启用自动范围时可用（服务端权威，场景 25） -->
              <div class="nic-ips">
                <div class="nic-ips-head">
                  <span class="nic-ips-title">IP 分配</span>
                  <span class="nic-ips-hint">（IP 创建后不可改地址，只能删除后重新分配）</span>
                  <span v-if="canManage" class="nic-ips-actions">
                    <el-button
                      size="small"
                      :disabled="card.removed || card.segmentId === null"
                      @click="addCardIp(card, 'manual')"
                    >
                      手动输入 IP
                    </el-button>
                    <el-button
                      size="small"
                      :disabled="
                        card.removed ||
                        card.segmentId === null ||
                        segmentSummary(card.segmentId)?.autoAllocEnabled === false
                      "
                      @click="addCardIp(card, 'auto')"
                    >
                      自动分配
                    </el-button>
                  </span>
                </div>
                <div v-if="card.segmentId === null" class="nic-ips-segment-hint">
                  请先选择网段，再分配 IP（手动输入或自动分配）
                </div>
                <div
                  v-else-if="segmentSummary(card.segmentId)?.autoAllocEnabled === false"
                  class="nic-ips-segment-hint"
                >
                  该网段未启用自动分配范围，只能手动分配
                </div>

                <!-- IP 列表：既有（含将删除）与待分配条目 -->
                <div v-if="card.ips.length > 0" class="nic-ip-list">
                  <div
                    v-for="ip in card.ips"
                    :key="ip.key"
                    class="nic-ip-row"
                    :class="{ 'nic-ip-row-removed': ip.removed }"
                  >
                    <template v-if="ip.id !== null">
                      <code class="nic-ip-address">{{ ip.address }}</code>
                      <el-tag v-if="isCurrentManagementIp(ip.id)" size="small" type="warning">管理 IP</el-tag>
                      <el-tag v-if="ip.removed" size="small" type="danger">将删除</el-tag>
                      <span v-if="canManage && !card.removed">
                        <el-button v-if="!ip.removed" link type="danger" size="small" @click="removeCardIp(card, ip.key)">
                          删除
                        </el-button>
                        <el-button v-else link type="primary" size="small" @click="restoreCardIp(card, ip.key)">
                          恢复
                        </el-button>
                      </span>
                    </template>
                    <template v-else>
                      <el-input
                        v-if="ip.mode === 'manual'"
                        v-model="ip.address"
                        placeholder="IPv4 地址，须落在所选网段 CIDR 内"
                        class="nic-ip-input"
                        :disabled="!canManage || card.removed"
                        @input="clearCardIpError(card.key, ip.key, 'address')"
                      />
                      <span v-else class="nic-ip-auto">自动分配（保存时由服务端在网段启用的自动范围内选址）</span>
                      <el-tag size="small" type="success">新增 · {{ ip.mode === 'manual' ? '手动' : '自动' }}</el-tag>
                      <span v-if="canManage && !card.removed">
                        <el-button link type="danger" size="small" @click="removeCardIp(card, ip.key)">移除</el-button>
                      </span>
                    </template>
                    <div v-if="fieldErrors.cards[card.key]?.ips[ip.key]?.address" class="nic-ip-error">
                      {{ fieldErrors.cards[card.key]?.ips[ip.key]?.address }}
                    </div>
                    <div v-else-if="fieldErrors.cards[card.key]?.ips[ip.key]?.other" class="nic-ip-error">
                      {{ fieldErrors.cards[card.key]?.ips[ip.key]?.other }}
                    </div>
                  </div>
                </div>
                <div v-else class="nic-ips-empty">
                  暂无 IP：无 IP 网卡可直接保存（如无 IP 的 IB 接口，§4.2.4）；分配 IP 前必须选定网段
                </div>
              </div>
            </div>

            <el-alert
              v-if="fieldErrors.cards[card.key]?.other"
              type="error"
              :closable="false"
              show-icon
              :title="fieldErrors.cards[card.key]?.other"
            />
          </el-card>
        </el-card>

        <!-- 管理 IP（§4.2.9：资源级引用，候选为本表单将保存的网卡 IP；§4.2.11 删除当前管理 IP/其网卡时须同次显式清空/重选） -->
        <el-card shadow="never" class="resource-section">
          <template #header><span class="resource-section-title">管理 IP</span></template>
          <el-form-item
            label="管理 IP（可选）"
            :error="fieldErrors.management_ip || undefined"
          >
            <el-select
              :model-value="managementIpValue"
              filterable
              placeholder="从本表单将保存的网卡 IP 中指定（可不指定）"
              class="resource-management-ip-select"
              :disabled="!canManage"
              @change="setManagementIpValue"
            >
              <el-option v-if="mode === 'edit'" :value="MANAGEMENT_IP_KEEP" :label="managementKeepLabel" />
              <el-option :value="MANAGEMENT_IP_NONE" label="无管理 IP（不指定 / 显式清空）" />
              <el-option
                v-for="c in managementIpCandidates"
                :key="c.value"
                :value="c.value"
                :label="c.label"
              />
            </el-select>
            <div class="resource-management-ip-hint">
              管理 IP 从该资源已登记（含本次将保存）的网卡 IP 中指定；删除当前管理 IP 或其所属网卡时，
              必须在同一次提交中显式清空或重选，否则整单拒绝（不会静默清空或改指）
            </div>
          </el-form-item>
        </el-card>

        <!-- 记录级提示（409 INTERFACE_NAME_TAKEN / NO_FIELDS 等；保留输入） -->
        <el-alert
          v-if="formNotice"
          type="error"
          :closable="false"
          show-icon
          :title="formNotice"
          class="resource-form-notice"
        />

        <!-- 并发冲突：保留输入，刷新确认后重提（§4.5、场景 47） -->
        <el-alert
          v-if="conflict"
          type="warning"
          :closable="false"
          show-icon
          class="resource-conflict"
          title="该资源已被其他人修改（并发冲突），当前输入已保留。请刷新确认后重新提交；不会静默覆盖他人修改。"
        >
          <el-button size="small" :loading="refreshingVersion" @click="refreshVersionKeepInput">
            刷新版本（保留当前输入）
          </el-button>
        </el-alert>
        <el-alert
          v-if="conflictResolved"
          type="info"
          closable
          show-icon
          class="resource-conflict"
          title="已更新到最新版本（当前输入已保留）。请确认内容后重新提交。"
          @close="handleConflictResolvedClose"
        />

        <!-- 操作 -->
        <div class="resource-actions">
          <el-button
            v-if="canManage"
            type="primary"
            :loading="submitting"
            :disabled="conflict"
            @click="submit"
          >
            {{ mode === 'create' ? '创建' : '保存' }}
          </el-button>
          <el-button @click="router.push({ name: 'clusters' })">返回</el-button>
          <el-button
            v-if="mode === 'edit' && canManage"
            type="danger"
            plain
            class="resource-delete-entry"
            @click="openDelete"
          >
            删除资源
          </el-button>
        </div>
      </el-form>
    </template>

    <!-- 同名确认（§4.1.10、场景 2/45：不创建第二条、不覆盖、不合并） -->
    <el-dialog
      :model-value="sameNamePrompt !== null"
      title="该集群已存在同名资源"
      width="480px"
      :close-on-click-modal="false"
      @update:model-value="handleSameNameDialog"
    >
      <p class="same-name-text">
        该集群已存在同名资源「<strong>{{ name }}</strong
        >」<template v-if="sameNamePrompt?.existingType">
          （{{ resourceTypeLabel(sameNamePrompt.existingType) }}）</template
        >。
      </p>
      <p class="same-name-text">
        不会创建第二条，也不会覆盖或合并。是否进入该资源的编辑？（原表单输入已保留，可取消后留在本页。）
      </p>
      <template #footer>
        <el-button @click="dismissSameName">留在本页</el-button>
        <el-button type="primary" @click="confirmSameNameGoEdit">进入编辑</el-button>
      </template>
    </el-dialog>

    <!-- 真实删除：二次确认须输入资源名称（BQ-Z）+ 删除前置提示 -->
    <el-dialog
      :model-value="deleteVisible"
      title="删除资源"
      width="540px"
      :close-on-click-modal="false"
      @update:model-value="handleDeleteDialog"
    >
      <template v-if="detail">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="真实删除不可恢复：删除前须逐项删除其全部网卡；审计与资源历史保留"
          class="delete-warning"
        />
        <p class="delete-target">
          将删除资源：<strong>{{ detail.name }}</strong>
          （{{ resourceTypeLabel(detail.resource_type) }}，集群 {{ detail.cluster_code }}
          {{ detail.cluster_name }}）
        </p>
        <el-alert
          v-if="remainingInterfaceCount > 0"
          type="warning"
          :closable="false"
          show-icon
          :title="`该资源仍有 ${remainingInterfaceCount} 张网卡：请先在表单中逐项删除全部网卡并保存，再删除资源`"
          class="delete-prereq"
        />
        <el-form @submit.prevent="submitDelete">
          <el-form-item label="请输入资源名称以确认删除" :error="deleteConfirmError || undefined">
            <el-input
              v-model="deleteConfirmInput"
              :placeholder="`输入「${detail.name}」（区分大小写）`"
              @input="deleteConfirmError = ''"
            />
          </el-form-item>
        </el-form>
        <el-alert v-if="deleteBlockError" type="error" :closable="false" show-icon :title="deleteBlockError">
          <el-button v-if="deleteVersionConflict" size="small" @click="refreshVersionKeepInput">
            刷新版本（保留确认输入）
          </el-button>
        </el-alert>
      </template>
      <template #footer>
        <el-button @click="closeDelete">取消</el-button>
        <el-button
          type="danger"
          :loading="deleteSubmitting"
          :disabled="!deleteConfirmMatched"
          @click="submitDelete"
        >
          删除
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.resource-form-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.resource-loading {
  min-height: 240px;
}
.resource-form-header {
  display: flex;
  align-items: baseline;
  gap: 16px;
}
.resource-form-title {
  margin: 0;
  font-size: 20px;
}
.resource-form-scope {
  color: #606266;
}
.resource-form-scope-hint {
  color: #909399;
  font-size: 12px;
}
.resource-readonly-notice {
  margin-bottom: 0;
}
.resource-section {
  width: 100%;
}
.resource-section-title {
  font-weight: 600;
}
.resource-field-row {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.resource-field-grow {
  flex: 1;
  min-width: 0;
}
.resource-cluster-select {
  width: 100%;
  max-width: 420px;
}
.resource-type-select,
.resource-status-select {
  width: 100%;
  max-width: 280px;
}
.resource-inline-error {
  width: 100%;
  color: #f56c6c;
  font-size: 12px;
  line-height: 20px;
}
.resource-status-info {
  margin-top: 4px;
}
.resource-nics-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.resource-nics-hint {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}
.resource-nics-loading {
  color: #909399;
  font-size: 12px;
}
.resource-nics-head .el-button {
  margin-left: auto;
}
.resource-segments-error {
  margin-bottom: 12px;
}
.nic-card {
  border: 1px solid #e4e7ed;
  margin-bottom: 12px;
}
.nic-card-removed {
  background-color: #fafafa;
  opacity: 0.75;
}
.nic-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.nic-card-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}
.nic-card-body-removed {
  pointer-events: none;
}
.resource-segment-select {
  width: 100%;
}
.nic-segment-info {
  margin-top: 4px;
}
.nic-ips {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed #e4e7ed;
}
.nic-ips-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.nic-ips-title {
  font-weight: 600;
  font-size: 13px;
}
.nic-ips-hint {
  color: #909399;
  font-size: 12px;
}
.nic-ips-actions {
  display: inline-flex;
  gap: 8px;
  margin-left: auto;
}
.nic-ips-segment-hint {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
.nic-ip-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.nic-ip-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.nic-ip-row-removed {
  opacity: 0.65;
}
.nic-ip-row-removed .nic-ip-address {
  text-decoration: line-through;
}
.nic-ip-address {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
}
.nic-ip-input {
  width: 280px;
}
.nic-ip-auto {
  color: #606266;
  font-size: 12px;
}
.nic-ip-error {
  width: 100%;
  color: #f56c6c;
  font-size: 12px;
  line-height: 1.4;
}
.nic-ips-empty {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
.resource-management-ip-select {
  width: 100%;
  max-width: 420px;
}
.resource-management-ip-hint {
  width: 100%;
  color: #909399;
  font-size: 12px;
  line-height: 1.5;
}
.resource-form-notice,
.resource-conflict {
  margin-bottom: 0;
}
.resource-actions {
  display: flex;
  gap: 8px;
}
.resource-delete-entry {
  margin-left: auto;
}
.resource-retry {
  margin-top: 12px;
}
.same-name-text {
  margin: 0 0 8px;
}
.delete-warning {
  margin-bottom: 12px;
}
.delete-target {
  margin: 0 0 12px;
}
.delete-prereq {
  margin-bottom: 12px;
}
</style>
