<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import {
  BranchesOutlined,
  CheckOutlined,
  CodeOutlined,
  CopyOutlined,
  DeploymentUnitOutlined,
  FileTextOutlined,
  PlusOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SendOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useIMStore } from '@/stores/im'

const im = useIMStore()
const listRef = ref(null)
const creatingRoom = ref(false)
const sending = ref(false)
const composer = ref('请帮我设计一个 React Button 组件，并说明实现思路')
const selectedMentions = ref([])
const roomForm = reactive({
  type: 'dm',
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

const visibleEvents = computed(() => {
  return im.events
    .filter((event) => !['message.created', 'room.created'].includes(event.name))
    .slice(-12)
    .reverse()
})

const roomAgentOptions = computed(() => {
  return im.executorAgents.map((agent) => ({
    label: `${agent.name} · ${agent.metadata?.agent_kind || 'native'}`,
    value: agent.agent_id,
  }))
})

const mentionOptions = computed(() => {
  return currentMembers.value.map((agent) => ({
    label: agent.name,
    value: agent.agent_id,
  }))
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

function avatarText(agentId, senderType = 'agent') {
  if (senderType === 'user') return 'U'
  if (senderType === 'system') return 'S'
  return (agentName(agentId) || 'A').slice(0, 1).toUpperCase()
}

function messageTitle(item) {
  if (item.sender_type === 'user') return '你'
  if (item.sender_type === 'system') return '系统'
  return agentName(item.sender_id)
}

function messageClass(item) {
  return {
    mine: item.sender_type === 'user',
    system: item.sender_type === 'system',
  }
}

function shortId(value = '') {
  return value ? value.slice(0, 8) : '-'
}

function formatTime(ts) {
  return ts ? new Date(ts * 1000).toLocaleTimeString() : ''
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
    selectedMentions.value = []
    message.success('房间已创建')
  } finally {
    creatingRoom.value = false
  }
}

async function send() {
  if (!im.currentRoom) {
    message.warning('请先创建或选择房间')
    return
  }
  if (!composer.value.trim()) return
  sending.value = true
  try {
    await im.sendMessage(
      {
        sender_type: 'user',
        sender_id: 'user',
        content_parts: [{ type: 'text', text: composer.value.trim() }],
        mentions: [...selectedMentions.value],
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
    selectedMentions.value = []
    await scrollToBottom()
  } finally {
    sending.value = false
  }
}

async function approveConfirmation(part) {
  const targetMessageId = part.metadata?.message_id
  if (!targetMessageId) return
  await im.recordAction(part.metadata?.message_id || targetMessageId, {
    action_type: 'approve',
    actor_id: 'user',
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
  const defaultExecutor = im.executorAgents.find((agent) => agent.agent_id === 'default_executor') || im.executorAgents[0]
  const defaultPlanner = im.plannerAgents.find((agent) => agent.agent_id === 'default_planner') || im.plannerAgents[0]
  if (defaultExecutor) roomForm.member_agent_ids = [defaultExecutor.agent_id]
  if (defaultPlanner) dispatchOptions.planner_agent_id = defaultPlanner.agent_id
  await scrollToBottom()
})
</script>

<template>
  <main class="im-shell">
    <aside class="room-rail">
      <div class="brand-row">
        <div class="brand-mark"><RobotOutlined /></div>
        <div>
          <h1>Agent IM</h1>
          <p>多 Agent 协作聊天</p>
        </div>
      </div>

      <section class="create-panel">
        <a-segmented v-model:value="roomForm.type" :options="['dm', 'group']" block />
        <a-input v-model:value="roomForm.title" placeholder="房间名称" />
        <a-select
          v-model:value="roomForm.member_agent_ids"
          :mode="roomForm.type === 'group' ? 'multiple' : undefined"
          :options="roomAgentOptions"
          placeholder="选择 agent"
          show-search
        />
        <a-button type="primary" block :loading="creatingRoom" @click="createRoom">
          <template #icon><PlusOutlined /></template>
          创建房间
        </a-button>
      </section>

      <a-list class="room-list" :data-source="im.rooms" :loading="im.loading">
        <template #renderItem="{ item }">
          <a-list-item
            class="room-item"
            :class="{ active: item.room_id === im.currentRoom?.room_id }"
            @click="im.selectRoom(item.room_id)"
          >
            <a-list-item-meta>
              <template #avatar>
                <a-avatar :class="item.type">
                  <TeamOutlined v-if="item.type === 'group'" />
                  <UserOutlined v-else />
                </a-avatar>
              </template>
              <template #title>{{ item.title }}</template>
              <template #description>
                {{ item.type }} · {{ item.member_agent_ids.length }} agents
              </template>
            </a-list-item-meta>
          </a-list-item>
        </template>
      </a-list>
    </aside>

    <section class="chat-column">
      <header class="chat-header">
        <div>
          <h2>{{ im.currentRoom?.title || '选择一个房间' }}</h2>
          <p>
            <span v-for="agent in currentMembers" :key="agent.agent_id">
              {{ agent.name }} · {{ agent.metadata?.agent_kind || 'native' }}
            </span>
          </p>
        </div>
        <a-space>
          <a-switch v-model:checked="dispatchOptions.auto_start" />
          <span class="switch-label">自动启动</span>
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
          <a-avatar class="message-avatar">{{ avatarText(item.sender_id, item.sender_type) }}</a-avatar>
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
        <a-select
          v-model:value="selectedMentions"
          mode="multiple"
          :options="mentionOptions"
          placeholder="@ 指定 agent，留空则按房间规则调度"
        />
        <a-textarea
          v-model:value="composer"
          :auto-size="{ minRows: 2, maxRows: 6 }"
          placeholder="输入消息，支持 @agent 指派；群聊留空 @ 时由 PlanOrchestrator 编排"
          @pressEnter.ctrl.prevent="send"
        />
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
    </section>

    <aside class="inspector">
      <section class="panel">
        <h3>房间 Agent</h3>
        <a-list :data-source="currentMembers">
          <template #renderItem="{ item }">
            <a-list-item>
              <a-list-item-meta>
                <template #avatar>
                  <a-avatar>{{ avatarText(item.agent_id) }}</a-avatar>
                </template>
                <template #title>{{ item.name }}</template>
                <template #description>
                  {{ item.agent_id }} · {{ item.metadata?.agent_kind || 'native' }}
                </template>
              </a-list-item-meta>
              <a-tag>{{ item.agent_type }}</a-tag>
            </a-list-item>
          </template>
        </a-list>
      </section>

      <section class="panel event-panel">
        <h3>实时事件</h3>
        <a-empty v-if="!visibleEvents.length" description="暂无事件" />
        <div v-for="event in visibleEvents" :key="event.event_id" class="event-line">
          <a-tag color="blue">{{ event.name }}</a-tag>
          <span>{{ formatTime(event.created_at) }}</span>
          <pre>{{ JSON.stringify(event.payload, null, 2) }}</pre>
        </div>
      </section>
    </aside>
  </main>
</template>
