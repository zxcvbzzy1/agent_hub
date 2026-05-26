<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  BranchesOutlined,
  CheckOutlined,
  CloudUploadOutlined,
  CopyOutlined,
  DeploymentUnitOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useIMStore } from '@/stores/im'

const im = useIMStore()
const auth = useAuthStore()
const listRef = ref(null)
const composerRef = ref(null)
const creatingRoom = ref(false)
const sending = ref(false)
const drawerOpen = ref(false)
const createOpen = ref(false)
const mentionOpen = ref(false)
const composer = ref('')
const mentions = ref([])
const roomForm = reactive({
  type: 'group',
  title: '',
  member_agent_ids: [],
})
const dispatchOptions = reactive({
  auto_start: false,
  planner_agent_id: 'default_planner',
  context_id: 'default_step',
  max_replan_rounds: 3,
})

const currentMembers = computed(() => {
  const ids = im.currentRoom?.member_agent_ids || []
  return ids.map(agentById).filter(Boolean)
})

const activeTitle = computed(() => {
  if (im.currentRoom) return im.currentRoom.title
  if (im.currentAgent) return im.currentAgent.name
  return '选择 Agent 或群聊'
})

const activeSubtitle = computed(() => {
  if (im.currentRoom?.type === 'group') return `${currentMembers.value.length} agents · PlanOrchestrator`
  if (im.currentAgent) return `${agentKind(im.currentAgent.agent_id)} · ${im.currentAgent.agent_type}`
  return '开始一次协作'
})

const roomAgentOptions = computed(() => {
  return im.executorAgents.map((agent) => ({
    label: `${agent.name} · ${agent.metadata?.agent_kind || 'native'}`,
    value: agent.agent_id,
  }))
})

const mentionCandidates = computed(() => {
  if (im.currentRoom?.type !== 'group' || !mentionOpen.value) return []
  const lastAt = composer.value.lastIndexOf('@')
  const query = lastAt >= 0 ? composer.value.slice(lastAt + 1).trim().toLowerCase() : ''
  return currentMembers.value.filter((agent) => {
    return !query || agent.name.toLowerCase().includes(query) || agent.agent_id.toLowerCase().includes(query)
  })
})

const sideItems = computed(() => {
  if (im.currentRoom?.type === 'group') return im.tasks
  if (im.currentAgentId) return im.agentMessages
  return []
})

function agentById(agentId) {
  return im.agents.find((agent) => agent.agent_id === agentId)
}

function agentName(agentId) {
  return agentById(agentId)?.name || agentId || 'unknown'
}

function agentKind(agentId) {
  return agentById(agentId)?.metadata?.agent_kind || 'native'
}

function avatarText(value = '') {
  return (value || 'A').slice(0, 1).toUpperCase()
}

function itemAvatar(item) {
  if (item.type === 'group') return avatarText(item.title)
  return avatarText(item.name)
}

function messageTitle(item) {
  if (item.sender_type === 'user') {
    return item.sender_id === auth.user?.user_id ? '你' : item.sender_id
  }
  if (item.sender_type === 'system') return '系统'
  return agentName(item.sender_id)
}

function messageClass(item) {
  return {
    mine: item.sender_type === 'user' && item.sender_id === auth.user?.user_id,
    system: item.sender_type === 'system',
  }
}

function shortId(value = '') {
  return value ? value.slice(0, 8) : '-'
}

function formatTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleTimeString() : ''
}

function latestMessageText(item) {
  const part = item.content_parts?.find((entry) => entry.text || entry.diff || entry.title)
  return part?.text || part?.diff || part?.title || item.prompt || item.final || '暂无内容'
}

async function createRoom() {
  if (!roomForm.member_agent_ids.length) {
    message.warning('请选择 agent')
    return
  }
  if (roomForm.type === 'dm' && roomForm.member_agent_ids.length !== 1) {
    message.warning('单聊只能选择一个 agent')
    return
  }
  creatingRoom.value = true
  try {
    await im.createRoom({
      type: roomForm.type,
      title: roomForm.title || (roomForm.type === 'dm' ? agentName(roomForm.member_agent_ids[0]) : 'Agent 群聊'),
      member_agent_ids: [...roomForm.member_agent_ids],
      metadata: { source: 'IM_front' },
    })
    createOpen.value = false
    roomForm.title = ''
    roomForm.type = 'group'
    roomForm.member_agent_ids = []
    message.success('房间已创建')
  } finally {
    creatingRoom.value = false
  }
}

function handleInput(event) {
  const value = event.target.value
  composer.value = value
  const lastAt = value.lastIndexOf('@')
  mentionOpen.value = im.currentRoom?.type === 'group' && lastAt >= 0 && !value.slice(lastAt + 1).includes(' ')
}

function insertMention(agent) {
  const lastAt = composer.value.lastIndexOf('@')
  const before = lastAt >= 0 ? composer.value.slice(0, lastAt) : composer.value
  composer.value = `${before}@${agent.name} `
  if (!mentions.value.includes(agent.agent_id)) mentions.value.push(agent.agent_id)
  mentionOpen.value = false
  nextTick(() => composerRef.value?.focus?.())
}

async function send() {
  if (!im.currentRoom && !im.currentAgentId) {
    message.warning('请选择 agent 或群聊')
    return
  }
  if (!composer.value.trim()) return
  sending.value = true
  try {
    await im.sendMessage(
      {
        sender_type: 'user',
        content_parts: [{ type: 'text', text: composer.value.trim() }],
        mentions: [...mentions.value],
        metadata: { client: 'IM_front' },
      },
      {
        auto_start: dispatchOptions.auto_start,
        planner_agent_id: dispatchOptions.planner_agent_id,
        context_id: dispatchOptions.context_id,
        max_replan_rounds: dispatchOptions.max_replan_rounds,
      },
    )
    composer.value = ''
    mentions.value = []
    mentionOpen.value = false
    await scrollToBottom()
  } finally {
    sending.value = false
  }
}

async function approveConfirmation(part) {
  const targetMessageId = part.metadata?.message_id
  if (!targetMessageId) return
  await im.recordAction(targetMessageId, {
    action_type: 'approve',
    payload: part.metadata,
  })
  await im.dispatch(targetMessageId, {
    approved: true,
    auto_start: true,
    planner_agent_id: dispatchOptions.planner_agent_id,
    context_id: dispatchOptions.context_id,
    max_replan_rounds: dispatchOptions.max_replan_rounds,
  })
  message.success('已批准并启动外部 Agent')
}

function copyText(text) {
  navigator.clipboard?.writeText(text)
  message.success('已复制')
}

async function scrollToBottom() {
  await nextTick()
  const el = listRef.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(
  () => im.messages.length,
  () => scrollToBottom(),
)

onMounted(async () => {
  await im.bootstrap()
  const defaultPlanner = im.plannerAgents.find((agent) => agent.agent_id === 'default_planner') || im.plannerAgents[0]
  if (defaultPlanner) dispatchOptions.planner_agent_id = defaultPlanner.agent_id
  await scrollToBottom()
})
</script>

<template>
  <main class="im-workspace">
    <aside class="im-sidebar">
      <div class="sidebar-head">
        <div>
          <h2>会话</h2>
          <span>{{ im.executorAgents.length }} agents · {{ im.rooms.length }} groups</span>
        </div>
        <a-button type="primary" shape="circle" @click="createOpen = true">
          <template #icon><PlusOutlined /></template>
        </a-button>
      </div>

      <section class="nav-section">
        <div class="section-title">Agents</div>
        <button
          v-for="agent in im.executorAgents"
          :key="agent.agent_id"
          class="nav-card"
          :class="{ active: im.currentAgentId === agent.agent_id && im.currentRoom?.type !== 'group' }"
          @click="im.selectAgent(agent.agent_id)"
        >
          <a-avatar :src="agent.metadata?.avatar_url">{{ itemAvatar(agent) }}</a-avatar>
          <span class="presence"></span>
          <div>
            <strong>{{ agent.name }}</strong>
            <small>{{ agentKind(agent.agent_id) }}</small>
          </div>
        </button>
      </section>

      <section class="nav-section">
        <div class="section-title">Agent 群</div>
        <button
          v-for="room in im.rooms.filter((item) => item.type === 'group')"
          :key="room.room_id"
          class="nav-card"
          :class="{ active: im.currentRoom?.room_id === room.room_id }"
          @click="im.selectRoom(room.room_id)"
        >
          <a-avatar :src="room.avatar_url"><TeamOutlined /></a-avatar>
          <div>
            <strong>{{ room.title }}</strong>
            <small>{{ room.member_agent_ids.length }} members</small>
          </div>
        </button>
      </section>

      <section class="side-feed">
        <div class="section-title">{{ im.currentRoom?.type === 'group' ? '编排任务' : '消息列表' }}</div>
        <a-empty v-if="!sideItems.length" description="暂无记录" />
        <button v-for="item in sideItems" :key="item.message_id || item.task_id" class="feed-item">
          <strong>{{ item.status || item.mode || 'message' }}</strong>
          <span>{{ latestMessageText(item) }}</span>
          <small>{{ formatTime(item.created_at) }}</small>
        </button>
      </section>
    </aside>

    <section class="chat-main">
      <header class="chat-hero">
        <div class="hero-title">
          <a-avatar :size="44">
            <TeamOutlined v-if="im.currentRoom?.type === 'group'" />
            <RobotOutlined v-else />
          </a-avatar>
          <div>
            <h1>{{ activeTitle }}</h1>
            <p>{{ activeSubtitle }}</p>
          </div>
        </div>
        <a-space>
          <a-switch v-model:checked="dispatchOptions.auto_start" />
          <span class="muted">自动启动</span>
        </a-space>
      </header>

      <div ref="listRef" class="message-list">
        <a-empty v-if="!im.messages.length" description="暂无消息" />
        <article
          v-for="item in im.messages"
          :key="item.message_id"
          class="message-row"
          :class="messageClass(item)"
        >
          <a-avatar class="message-avatar">{{ avatarText(messageTitle(item)) }}</a-avatar>
          <div class="message-bubble">
            <div class="message-meta">
              <strong>{{ messageTitle(item) }}</strong>
              <span>{{ formatTime(item.created_at) }}</span>
              <a-tag v-if="item.status !== 'sent'" size="small">{{ item.status }}</a-tag>
              <a-tag v-if="item.run_id" size="small" color="blue">run {{ shortId(item.run_id) }}</a-tag>
            </div>

            <div v-for="(part, index) in item.content_parts" :key="`${item.message_id}-${index}`" class="part">
              <p v-if="part.type === 'text'" class="text-part">{{ part.text }}</p>
              <pre v-else-if="part.type === 'code'" class="code-part"><code>{{ part.text }}</code></pre>
              <img v-else-if="part.type === 'image'" class="image-part" :src="part.url" :alt="part.name || 'image'" />
              <a-button v-else-if="part.type === 'file'" :href="part.url" target="_blank">
                <template #icon><FileTextOutlined /></template>
                {{ part.name || '文件' }}
              </a-button>
              <a :href="part.url" target="_blank" v-else-if="part.type === 'web_preview'" class="web-card">
                <strong>{{ part.title || part.url }}</strong>
                <span>{{ part.description }}</span>
              </a>
              <div v-else-if="part.type === 'diff'" class="diff-card">
                <div class="card-title">
                  <BranchesOutlined />
                  <span>{{ part.title || 'Diff' }}</span>
                  <a-button size="small" type="text" @click="copyText(part.diff)">
                    <template #icon><CopyOutlined /></template>
                  </a-button>
                </div>
                <pre><code>{{ part.diff }}</code></pre>
              </div>
              <div v-else-if="part.type === 'deploy'" class="deploy-card">
                <div class="card-title">
                  <DeploymentUnitOutlined />
                  <span>{{ part.title || '操作卡片' }}</span>
                </div>
                <p>{{ part.description }}</p>
                <a-space v-if="part.metadata?.message_id">
                  <a-button type="primary" size="small" @click="approveConfirmation(part)">
                    <template #icon><CheckOutlined /></template>
                    批准
                  </a-button>
                  <a-tag color="orange">
                    <SafetyCertificateOutlined />
                    人工确认
                  </a-tag>
                </a-space>
              </div>
              <a-tag v-else color="default">{{ part.type }}</a-tag>
            </div>
          </div>
        </article>
      </div>

      <footer class="composer">
        <div class="mention-wrap">
          <div v-if="mentionCandidates.length" class="mention-popover">
            <button v-for="agent in mentionCandidates" :key="agent.agent_id" @click="insertMention(agent)">
              <a-avatar :size="24">{{ avatarText(agent.name) }}</a-avatar>
              <span>{{ agent.name }}</span>
              <small>{{ agentKind(agent.agent_id) }}</small>
            </button>
          </div>
          <a-textarea
            ref="composerRef"
            :value="composer"
            :auto-size="{ minRows: 2, maxRows: 6 }"
            placeholder="输入消息。群聊里输入 @ 可选择群内 agent"
            @input="handleInput"
            @pressEnter.ctrl.prevent="send"
          />
        </div>
        <div class="composer-actions">
          <a-space>
            <a-select v-model:value="dispatchOptions.planner_agent_id" class="planner-select">
              <a-select-option v-for="agent in im.plannerAgents" :key="agent.agent_id" :value="agent.agent_id">
                {{ agent.name }}
              </a-select-option>
            </a-select>
            <a-input-number v-model:value="dispatchOptions.max_replan_rounds" :min="0" :max="10" />
          </a-space>
          <a-button type="primary" :loading="sending" @click="send">
            <template #icon><SendOutlined /></template>
            发送
          </a-button>
        </div>
      </footer>

      <a-button class="floating-info" type="primary" shape="circle" @click="drawerOpen = true">
        <template #icon><InfoCircleOutlined /></template>
      </a-button>
    </section>

    <a-modal v-model:open="createOpen" title="创建 Agent 会话" :footer="null">
      <a-form layout="vertical" @finish="createRoom">
        <a-form-item label="类型">
          <a-segmented v-model:value="roomForm.type" :options="['dm', 'group']" block />
        </a-form-item>
        <a-form-item label="名称">
          <a-input v-model:value="roomForm.title" placeholder="留空则自动命名" />
        </a-form-item>
        <a-form-item label="Agent">
          <a-select
            v-model:value="roomForm.member_agent_ids"
            :mode="roomForm.type === 'group' ? 'multiple' : undefined"
            :options="roomAgentOptions"
            placeholder="选择 agent"
            show-search
          />
        </a-form-item>
        <a-button type="primary" html-type="submit" block :loading="creatingRoom">创建</a-button>
      </a-form>
    </a-modal>

    <a-drawer v-model:open="drawerOpen" title="上下文信息" width="420">
      <section class="drawer-section">
        <h3>{{ im.currentRoom?.type === 'group' ? '群内 Agent' : 'Agent 信息' }}</h3>
        <a-list :data-source="im.currentRoom?.type === 'group' ? currentMembers : [im.currentAgent].filter(Boolean)">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar><a-avatar :src="item.metadata?.avatar_url">{{ avatarText(item.name) }}</a-avatar></template>
                <template #title>{{ item.name }}</template>
                <template #description>
                  {{ item.agent_id }} · {{ item.metadata?.agent_kind || 'native' }}
                </template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </section>

      <section class="drawer-section">
        <h3>上传文件</h3>
        <a-empty v-if="!im.artifacts.length" description="暂无文件" />
        <a-list :data-source="im.artifacts">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar><FileTextOutlined /></template>
                <template #title>{{ item.filename }}</template>
                <template #description>{{ item.content_type || 'file' }} · {{ item.size }} bytes</template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </section>

      <section v-if="im.currentRoom?.type === 'group'" class="drawer-section">
        <h3>最近任务</h3>
        <a-list :data-source="im.tasks.slice(0, 6)">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar><CloudUploadOutlined /></template>
                <template #title>{{ item.status || item.mode }}</template>
                <template #description>{{ item.prompt }}</template>
              </a-list-item-meta>
            </a-list-item>
          </template>
        </a-list>
      </section>
    </a-drawer>
  </main>
</template>
