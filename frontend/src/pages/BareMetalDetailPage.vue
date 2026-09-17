<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { BARE_METAL_HARDWARE_FIELDS, getBareMetal, getBareMetalRelated } from '../api/bareMetals'
import type {
  BareMetalHardwareField,
  BareMetalRead,
  RelatedResources,
} from '../api/bareMetals'
import { useAsyncQuery } from '../composables/useAsyncQuery'
import { useBareMetalDelete } from '../composables/useBareMetalDelete'
import ErrorState from '../components/ErrorState.vue'
import ListStates from '../components/ListStates.vue'
import BareMetalStatusTag from '../components/BareMetalStatusTag.vue'
import BareMetalFormDialog from '../components/BareMetalFormDialog.vue'

/**
 * 裸金属详情页（F002 产品页）。
 *
 * - 调用 GET /api/bare-metals/{id}（契约 §3.3，规范路径），展示全部 13 字段
 *   （契约 §2 封闭集合）：R-BM-007 七字段 null 渲染为「—」（与契约「返回 null
 *   而非省略」一致）；时间为不透明字符串原样展示；hostname 原样展示（契约 §7）；
 * - 404 NOT_FOUND（不存在或已被逻辑删除，两者不区分，契约 §9）→ 独立的
 *   「资源不存在或已被删除」态，与列表页 Empty（200 + items 为空）是不同状态
 *   （R-QUERY-004）；
 * - 状态修改入口（BareMetalFormDialog，PATCH 契约 §3.4）：status + R-BM-007
 *   七字段可编辑；hostname / cluster_id 不在 PATCH 可变集内，不提供编辑输入；
 * - 删除入口（ElPopconfirm）→ DELETE /api/bare-metals/{id}（契约 §3.5）。
 *   删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取 → 404 →
 *   既有独立 Not Found 态；409 按error.code 渲染冲突提示；401 交由全局会话
 *   失效处理；提交中 Loading 且禁重复提交。删除守卫由后端裁决（§21）；
 * - 修改 / 删除失败均按 error.code 分支渲染，不解析 message；
 * - F006：「查看虚拟机」入口 → 进入该宿主的虚拟机列表
 *   （GET /api/virtual-machines?bare_metal_id={id}，契约 f006-virtual-machine.md
 *   §3.2）；本页不重复呈现虚拟机列表数据（聚合视图归 F010，见下方关联资源区）；
 * - F004：「查看网络接口」入口 → 进入该宿主的网络接口列表
 *   （GET /api/network-interfaces?bare_metal_id={id}，契约
 *   f004-network-interface.md §3.2）；本页不重复呈现网络接口列表数据（聚合视图
 *   归 F010，见下方关联资源区）；
 * - F010：「关联资源」区（GET /api/bare-metals/{id}/related，契约
 *   f010-resource-detail.md §2，单一聚合端点）：与详情请求并行、独立管理三态；
 *   一次请求获知五类清单（NIC / IP / VM / Container / Service），每类遵循
 *   ListStates（Loading / Empty / Error）；Empty（200 + items == []）渲染为
 *   「该裸金属暂无××」而非错误，与页面级 404 Not Found 态（不同 data-state、
 *   不同文案）可区分（AC-13 / R-QUERY-004）；Empty 不触发全局会话失效
 *   （仅 UNAUTHENTICATED 触发）；每条目自带关系依据（AC-08：NIC→
 *   bare_metal_id；IP→network_interface_id；VM→bare_metal_id；Container→
 *   carrier_type + carrier_id；Service→carriers 原样展示，不做交集筛选）；
 *   前端不做任何关联推导 / 过滤（NQ-5 裁定 a1，一律消费聚合端点返回的五类
 *   清单）；可从条目直接进入对应资源详情（AC-17，保留返回上下文）。
 */
const props = defineProps<{ bareMetalId: number }>()

const emit = defineEmits<{
  back: []
  openVirtualMachines: [bareMetalId: number]
  openNetworkInterfaces: [bareMetalId: number]
  /** F010：从关联条目进入网络接口详情。 */
  openNetworkInterfaceDetail: [networkInterfaceId: number]
  /** F010：从关联条目进入 IP 地址详情（携带关系依据 network_interface_id，
   * 供 App 恢复返回链上下文）。 */
  openIpAddressDetail: [ipAddressId: number, networkInterfaceId: number]
  /** F010：从关联条目进入虚拟机详情。 */
  openVirtualMachineDetail: [virtualMachineId: number]
  /** F010：从关联条目进入容器详情。 */
  openContainerDetail: [containerId: number]
  /** F010：从关联条目进入服务详情。 */
  openServiceDetail: [serviceId: number]
}>()

const { data, loading, error, run } = useAsyncQuery(() => getBareMetal(props.bareMetalId))

const { deletingId, deleteErrorView, requestDelete, clearDeleteError } = useBareMetalDelete({
  // 删除成功（204）或目标已不存在（404，两者不区分）→ 重新读取：
  // 服务端按契约对已删资源返回 404 → 进入既有独立 Not Found 态。
  onRemoved: () => run(),
})

onMounted(() => {
  void run()
  // F010：关联聚合与详情并行读取；关联区仅在内容态渲染（主体 404 时两请求
  // 均 404，页面进入既有 Not Found 态，关联区不呈现）。
  void runRelated()
})

// ---- F010：关联资源（单一聚合端点，一次请求获知五类） ----

const {
  data: relatedData,
  loading: relatedRequestLoading,
  error: relatedError,
  run: runRelated,
} = useAsyncQuery(() => getBareMetalRelated(props.bareMetalId))

/**
 * 关联区 Loading 判定：聚合请求进行中，或首次请求尚未返回（data 与 error
 * 均为空），避免首帧闪现空内容（与列表页 isLoading 同一模式）。
 */
const relatedLoading = computed(
  () =>
    relatedRequestLoading.value ||
    (relatedData.value === null && relatedError.value === null),
)

/** 五类关联键（契约 §2 顶层字段集合，封闭）。 */
type RelatedCategoryKey = keyof RelatedResources

/** 各类条目（契约原样值，不做任何变换；未加载时为空数组，不参与 Empty 判定）。 */
function relatedItems<K extends RelatedCategoryKey>(key: K): RelatedResources[K]['items'] {
  return relatedData.value?.[key].items ?? ([] as RelatedResources[K]['items'])
}

/**
 * 各类 Empty 判定：聚合请求成功（200）且该类 items 为空（契约 §2 Empty
 * 语义；主体活跃而某类为空绝不产生 404）。渲染为「该裸金属暂无××」，
 * 不是错误，也不触发全局会话失效（AC-13）。
 */
function relatedEmpty(key: RelatedCategoryKey): boolean {
  return relatedData.value !== null && relatedData.value[key].items.length === 0
}

/** 各类 total（契约 §2：total == items.length）；未加载时为 0。 */
function relatedTotal(key: RelatedCategoryKey): number {
  return relatedData.value?.[key].total ?? 0
}

/** R-BM-007 硬件字段展示标签。 */
const HARDWARE_LABELS: Record<BareMetalHardwareField, string> = {
  vendor: '厂商',
  model: '型号',
  serial_number: '序列号',
  cpu: 'CPU',
  memory: '内存',
  gpu: 'GPU',
  storage: '存储',
}

interface DetailItem {
  key: string
  label: string
  /** 展示值：硬件字段 null → 「—」；其余为契约原样值。 */
  value: string
  /** 状态字段以标签渲染（R-BM-003 原始值）。 */
  isStatus?: boolean
}

/** 详情字段（顺序即展示顺序）；值为契约原样值，不做任何变换。 */
const detailItems = computed<DetailItem[]>(() => {
  const bareMetal = data.value
  if (bareMetal === null) return []
  return [
    { key: 'id', label: 'ID', value: String(bareMetal.id) },
    { key: 'cluster_id', label: '所属集群 ID', value: String(bareMetal.cluster_id) },
    { key: 'hostname', label: 'hostname', value: bareMetal.hostname },
    { key: 'status', label: '状态', value: bareMetal.status, isStatus: true },
    ...BARE_METAL_HARDWARE_FIELDS.map((field) => ({
      key: field,
      label: HARDWARE_LABELS[field],
      value: bareMetal[field] ?? '—',
    })),
    { key: 'created_at', label: '登记时间', value: bareMetal.created_at },
    { key: 'updated_at', label: '更新时间', value: bareMetal.updated_at },
  ]
})

/**
 * 展示状态：
 * - not-found 是独立的 404 态（「资源不存在或已被删除」），
 *   与列表 Empty、其他 Error 均可区分（AC-30 / R-QUERY-004）；
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

/** F006：进入该宿主的虚拟机列表（携带 bare_metal_id）。 */
function openVirtualMachines(): void {
  emit('openVirtualMachines', props.bareMetalId)
}

/** F004：进入该宿主的网络接口列表（携带 bare_metal_id）。 */
function openNetworkInterfaces(): void {
  emit('openNetworkInterfaces', props.bareMetalId)
}

// ---- F010：从关联条目进入对应资源详情（AC-17，保留返回上下文）。 ----

function openRelatedNetworkInterface(networkInterfaceId: number): void {
  emit('openNetworkInterfaceDetail', networkInterfaceId)
}

function openRelatedIpAddress(ipAddressId: number, networkInterfaceId: number): void {
  emit('openIpAddressDetail', ipAddressId, networkInterfaceId)
}

function openRelatedVirtualMachine(virtualMachineId: number): void {
  emit('openVirtualMachineDetail', virtualMachineId)
}

function openRelatedContainer(containerId: number): void {
  emit('openContainerDetail', containerId)
}

function openRelatedService(serviceId: number): void {
  emit('openServiceDetail', serviceId)
}

/** 二次确认通过后删除当前裸金属；状态管理与错误渲染见 useBareMetalDelete。 */
function confirmDelete(): void {
  void requestDelete(props.bareMetalId)
}

// ---- 状态 / 硬件字段修改入口（PATCH） ----

const editDialogVisible = ref(false)

function handleUpdated(): void {
  // 保存成功 → 重新读取详情（data 更新为服务端返回的最新值）。
  void run()
}
</script>

<template>
  <main class="bare-metal-detail" :data-state="state">
    <header class="bare-metal-detail__header">
      <div class="bare-metal-detail__nav">
        <el-button @click="backToList">返回列表</el-button>
        <h1 class="bare-metal-detail__title">裸金属详情</h1>
      </div>
      <!-- 状态 / 硬件字段修改入口与删除入口：仅内容态出现；hostname / cluster_id
           不可变（契约 §3.4），不提供编辑；删除守卫由后端 409 裁决（§21）。
           F006「查看虚拟机」与 F004「查看网络接口」入口：跳转对应宿主过滤列表。 -->
      <div v-if="state === 'content'" class="bare-metal-detail__actions">
        <el-button type="primary" plain data-testid="open-virtual-machines" @click="openVirtualMachines">
          查看虚拟机
        </el-button>
        <el-button
          type="primary"
          plain
          data-testid="open-network-interfaces"
          @click="openNetworkInterfaces"
        >
          查看网络接口
        </el-button>
        <el-button type="primary" plain data-testid="open-edit-dialog" @click="editDialogVisible = true">
          编辑
        </el-button>
        <el-popconfirm
          title="确定删除该裸金属吗？删除后不可恢复。"
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

    <section class="bare-metal-detail__body">
      <div v-if="state === 'loading'" class="bare-metal-detail__loading">
        <el-skeleton :rows="4" animated />
      </div>
      <!-- 404（不存在或已被逻辑删除）与其他错误均按 error.code 分支渲染（ErrorState）。 -->
      <ErrorState v-else-if="error !== null" :error="error" />
      <template v-else>
        <!-- 删除失败提示（409 等）：与详情内容同现，按 error.code 渲染，可关闭。 -->
        <div
          v-if="deleteErrorView !== null"
          class="bare-metal-detail__delete-error"
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
            <BareMetalStatusTag v-if="item.isStatus" :status="item.value" />
            <template v-else>{{ item.value }}</template>
          </el-descriptions-item>
        </el-descriptions>

        <!-- F010 关联资源：一次请求（单一聚合端点）获知五类；前端不自行推导。
             每类遵循 ListStates 三态；Empty 与页面级 Not Found 是不同
             data-state / 文案（AC-13）；每条自带关系依据（AC-08）。 -->
        <section class="bare-metal-related" data-testid="related-resources">
          <h2 class="bare-metal-related__title">关联资源</h2>

          <!-- 网络接口（1 跳：nic.bare_metal_id = B.id） -->
          <section class="bare-metal-related__category" data-related="network_interfaces">
            <h3 class="bare-metal-related__category-title">
              网络接口
              <span v-if="relatedData !== null" class="bare-metal-related__count">
                （共 {{ relatedTotal('network_interfaces') }} 项）
              </span>
            </h3>
            <ListStates
              :loading="relatedLoading"
              :error="relatedError"
              :empty="relatedEmpty('network_interfaces')"
              empty-description="该裸金属暂无网络接口"
            >
              <el-table :data="relatedItems('network_interfaces')" size="small">
                <el-table-column prop="id" label="ID" width="72" />
                <el-table-column prop="name" label="名称" min-width="120" />
                <el-table-column prop="technology_type" label="技术类型" min-width="100" />
                <el-table-column prop="purpose" label="用途" min-width="96" />
                <el-table-column label="关系依据" min-width="200">
                  <template #default="{ row }">
                    <span data-testid="related-evidence">
                      宿主裸金属 #{{ row.bare_metal_id }}（bare_metal_id）
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="72">
                  <template #default="{ row }">
                    <el-button
                      link
                      type="primary"
                      data-testid="related-detail"
                      @click="openRelatedNetworkInterface(row.id)"
                    >
                      详情
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </ListStates>
          </section>

          <!-- IP 地址（2 跳：IP 无 bare_metal_id，经 network_interface_id → B 的 NIC） -->
          <section class="bare-metal-related__category" data-related="ip_addresses">
            <h3 class="bare-metal-related__category-title">
              IP 地址
              <span v-if="relatedData !== null" class="bare-metal-related__count">
                （共 {{ relatedTotal('ip_addresses') }} 项）
              </span>
            </h3>
            <ListStates
              :loading="relatedLoading"
              :error="relatedError"
              :empty="relatedEmpty('ip_addresses')"
              empty-description="该裸金属暂无 IP 地址"
            >
              <el-table :data="relatedItems('ip_addresses')" size="small">
                <el-table-column prop="id" label="ID" width="72" />
                <el-table-column prop="ip_address" label="IP 地址" min-width="150" />
                <el-table-column label="关系依据" min-width="220">
                  <template #default="{ row }">
                    <span data-testid="related-evidence">
                      所属网络接口 #{{ row.network_interface_id }}（network_interface_id）
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="72">
                  <template #default="{ row }">
                    <el-button
                      link
                      type="primary"
                      data-testid="related-detail"
                      @click="openRelatedIpAddress(row.id, row.network_interface_id)"
                    >
                      详情
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </ListStates>
          </section>

          <!-- 虚拟机（1 跳：vm.bare_metal_id = B.id） -->
          <section class="bare-metal-related__category" data-related="virtual_machines">
            <h3 class="bare-metal-related__category-title">
              虚拟机
              <span v-if="relatedData !== null" class="bare-metal-related__count">
                （共 {{ relatedTotal('virtual_machines') }} 项）
              </span>
            </h3>
            <ListStates
              :loading="relatedLoading"
              :error="relatedError"
              :empty="relatedEmpty('virtual_machines')"
              empty-description="该裸金属暂无虚拟机"
            >
              <el-table :data="relatedItems('virtual_machines')" size="small">
                <el-table-column prop="id" label="ID" width="72" />
                <el-table-column prop="name" label="名称" min-width="140" />
                <el-table-column label="关系依据" min-width="200">
                  <template #default="{ row }">
                    <span data-testid="related-evidence">
                      宿主裸金属 #{{ row.bare_metal_id }}（bare_metal_id）
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="72">
                  <template #default="{ row }">
                    <el-button
                      link
                      type="primary"
                      data-testid="related-detail"
                      @click="openRelatedVirtualMachine(row.id)"
                    >
                      详情
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </ListStates>
          </section>

          <!-- 容器（1~2 跳：载体为 B 或 B 上的活跃 VM，含间接；BQ-1 裁定） -->
          <section class="bare-metal-related__category" data-related="containers">
            <h3 class="bare-metal-related__category-title">
              容器
              <span v-if="relatedData !== null" class="bare-metal-related__count">
                （共 {{ relatedTotal('containers') }} 项）
              </span>
            </h3>
            <ListStates
              :loading="relatedLoading"
              :error="relatedError"
              :empty="relatedEmpty('containers')"
              empty-description="该裸金属暂无容器"
            >
              <el-table :data="relatedItems('containers')" size="small">
                <el-table-column prop="id" label="ID" width="72" />
                <el-table-column prop="name" label="名称" min-width="140" />
                <el-table-column label="关系依据" min-width="260">
                  <template #default="{ row }">
                    <span data-testid="related-evidence">
                      载体 {{ row.carrier_type }} #{{ row.carrier_id }}（carrier_type + carrier_id）
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="72">
                  <template #default="{ row }">
                    <el-button
                      link
                      type="primary"
                      data-testid="related-detail"
                      @click="openRelatedContainer(row.id)"
                    >
                      详情
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </ListStates>
          </section>

          <!-- 服务（1~3 跳：载体与 R(B) 有交集，含间接；BQ-2 裁定； carriers
               原样展示全部绑定，不做交集筛选） -->
          <section class="bare-metal-related__category" data-related="services">
            <h3 class="bare-metal-related__category-title">
              服务
              <span v-if="relatedData !== null" class="bare-metal-related__count">
                （共 {{ relatedTotal('services') }} 项）
              </span>
            </h3>
            <ListStates
              :loading="relatedLoading"
              :error="relatedError"
              :empty="relatedEmpty('services')"
              empty-description="该裸金属暂无服务"
            >
              <el-table :data="relatedItems('services')" size="small">
                <el-table-column prop="id" label="ID" width="72" />
                <el-table-column prop="name" label="名称" min-width="140" />
                <el-table-column label="关系依据" min-width="280">
                  <template #default="{ row }">
                    <div class="bare-metal-related__carriers" data-testid="related-evidence">
                      <span>载体绑定（carriers）：</span>
                      <el-tag
                        v-for="carrier in row.carriers"
                        :key="`${carrier.carrier_type}:${carrier.carrier_id}`"
                        size="small"
                        class="bare-metal-related__carrier"
                      >
                        {{ carrier.carrier_type }} #{{ carrier.carrier_id }}
                      </el-tag>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="72">
                  <template #default="{ row }">
                    <el-button
                      link
                      type="primary"
                      data-testid="related-detail"
                      @click="openRelatedService(row.id)"
                    >
                      详情
                    </el-button>
                  </template>
                </el-table-column>
              </el-table>
            </ListStates>
          </section>
        </section>
      </template>
    </section>

    <!-- 编辑表单（PATCH）：status + R-BM-007 七字段；hostname / cluster_id 不在其中。 -->
    <BareMetalFormDialog
      v-model="editDialogVisible"
      mode="edit"
      :bare-metal="data"
      @success="handleUpdated"
    />
  </main>
</template>

<style scoped>
.bare-metal-detail {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}

.bare-metal-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.bare-metal-detail__nav {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bare-metal-detail__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bare-metal-detail__title {
  margin: 0;
  font-size: 20px;
}

.bare-metal-detail__body {
  margin-top: 16px;
}

.bare-metal-detail__loading {
  padding: 8px 0;
}

.bare-metal-detail__delete-error {
  margin-bottom: 16px;
}

.bare-metal-related {
  margin-top: 32px;
}

.bare-metal-related__title {
  margin: 0 0 12px;
  font-size: 16px;
}

.bare-metal-related__category {
  margin-top: 16px;
}

.bare-metal-related__category-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.bare-metal-related__count {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.bare-metal-related__carriers {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
</style>
