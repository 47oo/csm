# Product Handoff — F017 应用外壳侧边栏导航

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-18
> Feature: **F017 — 应用外壳侧边栏导航**（App Shell Sidebar Navigation）
> 上游决策：用户 2026-09-18 就 `DEC-020` 明确裁定「做」——把应用外壳导航改为侧边栏，范围限于呈现层。

---

## Feature

**F017 — 应用外壳侧边栏导航**（App Shell Sidebar Navigation）

- Epic：E07「平台基础能力」（`project-plan.yaml`）
- 层级：`{database: false, backend: false, frontend: true}`
- Contract：`NOT_REQUIRED`
- 上游决策：用户 2026-09-18 就 `DEC-020` 明确裁定「做」——把应用外壳导航改为侧边栏，范围限于呈现层。

## Problem

**谁在什么情况下使用**：CSM 的内部运维人员在日常工作中通过应用外壳（`frontend/src/App.vue`）在 7 个资源区（集群 / 裸金属 / 虚拟机 / 网络接口 / IP 地址 / 容器 / 服务）之间导航。

**实际问题**：当前导航以顶部横向 `<header>` 中的一排 `<el-button>` 呈现。用户在已部署的生产实例上希望改为**左侧纵向侧边栏**形态，以获得更清晰、更符合运维平台习惯的导航布局（横向排布随导航项文案长度 / 窗口宽度变化而受挤压，纵向侧边栏更利于后续阅读与点击）。

**本 Feature 解决的是呈现问题，不是业务问题**：它改变导航的**外观与位置**，不改变任何资源的登记、查询、关系、状态、唯一性或生命周期行为，也不改变用户可达的页面集合。

> 说明：本 Feature 的**成立**（是否要做）与**范围边界**（限于呈现层）均已由用户在 `DEC-020` 中确认；产品阶段的任务是把范围与验收标准固化为可交给 Architecture / Frontend 的结构化需求，**不是**重新论证是否要做。

## Confirmed Requirements

以下均为用户已确认的范围（来源：用户 `DEC-020` 裁定 + `project-plan.yaml` `features[F017]`）：

1. **导航改为侧边栏形态**：应用外壳的导航区由顶部横向按钮改为**左侧纵向**呈现。
2. **7 个资源区在侧边栏全部可达**：集群 / 裸金属 / 虚拟机 / 网络接口 / IP 地址 / 容器 / 服务，点击后进入对应资源列表，与改版前一致。
3. **当前所在资源区高亮**：高亮行为（当前区唯一高亮、切换后随之更新）与改版前等价。
4. **用户名与登出入口仍然可用**：登出后回到登录页，既有幂等语义（204 与 401 归一处理）不变。
5. **登录页与 bootstrap 加载态不受影响**：未认证访问仍进登录页，已认证仍直接进入系统。
6. **既有视图切换与返回链路不被破坏**：各资源列表 ↔ 详情、从裸金属详情「关联资源」进入子资源详情后的返回目标、集群 / 宿主过滤上下文的恢复，行为与改版前一致。
7. **5 个既有导航测试文件中的 15 处活跃态断言必须「改写」而非「删除」**（见 AC-06）。
8. **工程门禁通过**：`npm run typecheck && npm run test && npm run build`。

## Confirmed Domain Rules

本 Feature **不新增、不修改任何领域规则**。它只影响应用外壳的导航呈现，不触及任何资源类型、分类、关系、状态、唯一性或生命周期。

**已确认领域规则中，没有一条规定导航形态**，逐项核实如下：

| 来源 | 内容 | 对本 Feature 的含义 |
| --- | --- | --- |
| `docs/product/requirements.md` §5 | 「分类的作用是帮助：产品组织；**页面导航**；查询；领域理解。」 | 这是对**资源分类作用**的陈述，不是对**导航形态**的要求。导航是否需要侧边栏 / 顶栏 / 图标 / 布局 / 响应式 / 移动端，需求文档**均未规定**。 |
| `docs/architecture/f002-bare-metal-handoff.md:230` | 「沿用无 vue-router 现状，**导航形式不构成产品规则**」 | 已明确：导航形态由实现层决定，不构成产品规则。 |
| `frontend/src/App.vue:31 / 93`（另 `:23` 为「仍不引入 vue-router」的既有注释，不支撑本结论） | 多处注释写明「导航形式不构成产品规则」 | 同上，代码内已固化的既有共识。 |
| `docs/product/domain-model.md` §3–§9 | 资源分类、关系、状态、唯一性、生命周期 | 与导航形态**无任何关联**；本 Feature 不改变其中任何一条。 |
| `docs/product/domain-model.md` §10 待确认项 | 待确认事项清单 | 与本 Feature **无关**，不涉及。 |

**结论**：改为侧边栏**不违反任何已确认规则**，也**不新增任何产品规则**。本次改动**不改变任何业务行为**，因为：

- 侧边栏承载的是与现在**完全相同**的 7 个导航目标（`openClusterList` / `openBareMetalList` / `openVirtualMachineList` / `openNetworkInterfaceList` / `openIpAddressList` / `openContainerList` / `openServiceList`）；
- 活跃态仍由既有、与布局无关的 computed `navSection`（`App.vue`）驱动，导航形态改变不改变该计算的输入（`resourceView.kind`）或输出；
- 视图切换（`ResourceView` 联合类型 + `open*` / `back*`）逻辑、返回上下文（`clusterId` / `returnClusterId` / `returnView`）**均不涉及导航布局**，本次不改；
- 用户名显示与登出处理（`handleLogout` → `resetToLogin`）位于 `app-shell__session`，其**业务语义**与位置无关。

**独立判断确认**：逐条检查了 `requirements.md`、`domain-model.md`、`resource-domain` Skill 以及相关架构 handoff，**未发现任何会被本次改动影响的已确认规则**（与用户预期一致）。

## Scope

### 本次包含

1. 将应用外壳导航区从顶部横向改为**左侧纵向侧边栏**（呈现层）。
2. 保持 7 个资源区导航目标与可达性不变。
3. 保持「当前所在资源区」高亮语义（唯一、正确、随切换更新）在侧边栏中**等价呈现**。
4. 保持用户名与登出入口可用，保持登录页与 bootstrap 加载态行为不变。
5. 保持既有视图切换与「返回」链路（含 F010 关联资源返回目标、集群 / 宿主过滤上下文恢复）行为不变。
6. **改写** 5 个既有导航测试文件中把活跃态断言为 `el-button--primary` 的 **15 处**（各文件 3 处，`appContainerNavigation` / `appServiceNavigation` / `appNetworkInterfaceNavigation` / `appVirtualMachineNavigation` / `appIpAddressNavigation`）为侧边栏活跃态的等价断言。
7. 确保 `frontend/tests/f009ClusterResourceView.spec.ts` 对 `src/App.vue` 的源码 token 扫描（`restore` / `undelete` / `include_deleted` / `回收站` / `恢复`）通过。
8. 通过工程门禁：`npm run typecheck && npm run test && npm run build`。

### 本次明确不包含

以下均为用户 `DEC-020` 明确限定或 `project-plan.yaml` 已固化的排除项：

1. **不引入 `vue-router`**：沿用 App.vue 内的极简视图状态（`ResourceView` 联合类型 + `open*` / `back*` 函数）。
2. **不新增任何前端依赖**：沿用既有 Element Plus（以及既有测试栈）。
3. **不改路由 / URL**：不引入 hash / history 路由，导航点击不改变地址栏。
4. **不改任何资源页面的内容与业务行为**：`pages/**`、`components/**` 的资源登记、查询、关系、状态、删除等逻辑不动。
5. **不改后端 / API 契约 / 数据库**：无新端点、无契约变更、无 migration。
6. **不做移动端 / 响应式适配**：不引入断点、抽屉式折叠、小屏布局。
7. **不做主题 / 换肤 / 深色模式**。
8. **不新增导航项或资源类型**：导航目标保持既有 7 个。
9. **不新增 / 不修改任何产品规则**（见 Confirmed Domain Rules）。

### 本次未涉及

以下内容当前需求**没有要求**，但**不得据此推断为永远不需要**（不阻塞、不代表排除）：

- 侧边栏是否可折叠 / 展开；
- 导航项是否附带图标；
- 是否记忆折叠状态（如 localStorage 持久化）；
- 侧边栏宽度取值或是否可拖拽调整；
- 是否按资源分类分组（Infrastructure / Virtual / Network / Service）呈现子层级；
- 导航项键盘可达性 / 无障碍增强；
- 导航形态的自动化视觉回归（截图对比）测试。

这些仅标记为「本次需求未涉及」，不作为本次范围的隐含承诺。

## Acceptance Criteria

以下各条均为**用户可观察的界面行为**，判定为「是 / 否」。AC 只描述用户看到什么，不规定任何实现选择。

- **AC-01（侧边栏呈现 + 7 区可达）**：应用外壳的导航以**左侧纵向**布局呈现，不再是顶部横向排列；侧边栏中包含且仅包含 7 个资源区入口——集群 / 裸金属 / 虚拟机 / 网络接口 / IP 地址 / 容器 / 服务；逐个点击每个入口，均进入对应的资源列表页，列表可正常加载。
- **AC-02（高亮唯一且正确）**：任一时刻，侧边栏中**有且仅有当前所在资源区**处于明确的活跃高亮态；切换到另一资源区后，原区高亮消失、新区高亮出现；该行为覆盖全部 7 个区，且各资源列表与详情页均归属其所属资源区（例如从「集群」进入的裸金属详情仍高亮「裸金属」，从侧边栏直接进入的全局裸金属列表亦高亮「裸金属」）。
- **AC-03（用户名与登出可用）**：已登录状态下，用户名与「登出」入口在界面中仍然可见可用；点击登出后回到登录页；登出请求返回 401（会话本已失效）与返回 204 时，用户观察到的结果一致（均回到登录页），与改版前行为相同。
- **AC-04（登录页与 bootstrap 不受影响）**：未认证访问应用时进入登录页；已有有效会话时直接进入系统（跳过登录页）；会话探测进行中显示既有 bootstrap 加载态。三种状态的可观察行为与改版前一致，侧边栏仅在进入系统后出现。
- **AC-05（视图切换与返回链路不破坏）**：
  - 各资源「列表 ↔ 详情」双向可达，进入详情后「返回」回到正确的列表；
  - 从裸金属详情「关联资源」进入网络接口 / IP 地址 / 虚拟机 / 容器 / 服务子详情后，「返回列表」回到**该裸金属详情**（而非全局子资源列表）；
  - 从集群详情进入「该集群的裸金属」后返回，回到**该集群详情**；从宿主裸金属详情进入「该宿主的虚拟机 / 网络接口」后返回，回到**该裸金属详情**；进一步进入 IP 地址列表后返回，回到**原网络接口详情**——即集群 / 宿主过滤上下文被正确恢复，均与改版前一致。
- **AC-06（必需工作：改写而非删除 15 处断言）**：5 个既有导航测试文件（`appContainerNavigation` / `appServiceNavigation` / `appNetworkInterfaceNavigation` / `appVirtualMachineNavigation` / `appIpAddressNavigation`）中把「活跃态」断言为 `el-button--primary` 的 **15 处**（各 3 处）必须**改写**为对侧边栏活跃态的等价断言——**不得删除、不得 skip、不得削弱**其验证的真实行为。改写后，断言必须仍能实际验证「当前所在资源区高亮正确、且仅当前区高亮」：即对当前区断言为活跃态、对非当前区断言为非活跃态（如测试原有三次断言的结构：当前区高亮、切走后不再高亮、切换目标区高亮）。若仅把断言改成恒真或删去其中之一，即视为未满足本 AC。
  - **`f009ClusterResourceView.spec.ts` 的源码 guard 不得删除**：该文件对 `src/App.vue` 等源码的 token 扫描（`restore` / `undelete` / `include_deleted` / `回收站` / `恢复`）为既有回归保护，必须保留。若侧边栏布局引入的措辞触发了该扫描，须按该文件既有取向（「只扫代码不扫注释」，已 `replace` 掉「不可恢复 / 恢复该上下文 / 返回时恢复」等合法注释措辞）处理扫描范围，**不得直接删除该 guard，也不得移除其检查的 token 语义**。
- **AC-07（工程门禁）**：`npm run typecheck && npm run test && npm run build` 全部通过；且 `npm run test` **连续运行 2 次**均全绿（前端基线以规划时的 40 files / 618 tests 为参照，最终用例数可因断言改写而合理变动，但不得低于改写前覆盖的真实行为数）。
- **AC-08（范围边界，可观察的「不做」）**：改版后——地址栏 URL 在导航切换时**不发生变化**（无路由）；`package.json` 依赖列表**未新增**任何前端依赖；后端 / `docs/api/**` / 数据库 migration **无改动**；资源页面的可观察内容与操作（登记、查询、关系、状态、删除入口等）与改版前**逐项一致**；导航项仍为既有 7 个；无移动端抽屉 / 响应式断点 / 主题切换入口出现。

> 注：AC 中不出现任何实现机制要求（例如「必须使用 `el-menu`」「必须使用某个 CSS 属性」）；实现选择由 Architecture / Frontend 决定。

## Assumptions

（仅在**不阻塞**当前工作、且可安全暂时采用时列出；均**不**伪装为 CONFIRMED。）

- A-1：改版后导航目标与 `data-testid`（`nav-clusters` / `nav-bare-metals` / `nav-virtual-machines` / `nav-network-interfaces` / `nav-ip-addresses` / `nav-containers` / `nav-services`）保持不变，以便测试定位——此为**合理假设**，用于支持 AC-06 的等价改写；如实现选择改变定位方式，Frontend 须同步更新测试定位而非削弱断言。
- A-2：本次不改变 7 个导航项的中文标签文案（集群 / 裸金属 / 虚拟机 / 网络接口 / IP 地址 / 容器 / 服务）。
- A-3：生产实例（`http://192.168.10.221/`）上真实用户的登录、登出与各资源区可达性在改版后不受影响——此为**部署验收的最低要求**，具体由实现与验证阶段核验。

## Proposed Rules

无。本 Feature **不提出任何新的产品规则**（PROPOSED 为空）。

> 如需为未来导航形态建立正式产品规则（例如「导航形态由实现层决定，不构成产品规则」升级为文档条目），属于**另一次产品决策**，不在本 Feature 范围内。

## Open Questions

### Blocking

**无。**

本 Feature 的成立与范围边界已由用户 `DEC-020`（2026-09-18）明确裁定，`project-plan.yaml` `features[F017]` 已固化 AC-01 ~ AC-08 草案；无任何阻塞当前定义的问题。

### Non-blocking

- **NQ-1**：侧边栏是否支持折叠 / 展开？
- **NQ-2**：导航项是否附带图标？
- **NQ-3**：是否记忆折叠状态（如 localStorage 持久化）？
- **NQ-4**：侧边栏宽度取值，或是否允许用户拖拽调整宽度？
- **NQ-5**：是否按资源分类（Infrastructure / Virtual / Network / Service）对导航项分组？

## Architecture Handoff

交给 Architect 的技术设计问题（**不替其选择框架、设计表或定义 API**）：

1. **侧边栏布局方案**：如何在 `App.vue` 应用外壳中实现左侧纵向侧边栏布局（保持 `app-shell` 结构语义、不引入新依赖、沿用 Element Plus）。
2. **活跃态表达方式**：在不改变既有 computed `navSection` 语义的前提下，选择侧边栏活跃态的呈现机制（并由 Frontend 据此改写 5 个测试文件的 15 处断言）。
3. **导航目标与视图状态解耦确认**：确认侧边栏仅改变呈现，不动 `ResourceView`、`open*` / `back*`、返回上下文（`returnView` / `returnClusterId`）逻辑。
4. **测试定位策略**：确定 `data-testid` 或等价定位方式在侧边栏实现下仍然稳定，以保证 AC-06 的等价断言可写、可验证。
5. **对 `f009ClusterResourceView.spec.ts` 源码 guard 的影响评估**：评估侧边栏样式 / 结构 / 注释是否引入 `restore` / `undelete` / `include_deleted` / `回收站` / `恢复` token，如触发则确定按「只扫代码不扫注释」取向的最小调整方案（不得删除 guard）。
6. **门禁与验证**：明确 typecheck / test（连跑 2 次）/ build 的执行方式，以及生产实例（登录、登出、7 区可达）的验证方法。

> Contract 预期为 `NOT_REQUIRED`（无 API / 后端 / 数据库变更），由 Architecture 阶段确认。

## Handoff Status

`READY FOR ARCHITECT`
