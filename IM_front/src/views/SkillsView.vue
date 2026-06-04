<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlusOutlined,
  DeleteOutlined,
  SaveOutlined,
  BookOutlined,
  TagsOutlined,
  FileTextOutlined,
} from '@ant-design/icons-vue'
import { listSkills, getSkill, createSkill, updateSkill, deleteSkill } from '@/api/skills'

// ── state ────────────────────────────────────────────────────────────────────
const skills = ref([])
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)

const isNew = ref(false)
const activeId = ref(null)

const form = reactive({
  id: '',
  name: '',
  description: '',
  tags: [],
  content: '',
  source: '',
})

// ── helpers ──────────────────────────────────────────────────────────────────
function resetForm() {
  form.id = ''
  form.name = ''
  form.description = ''
  form.tags = []
  form.content = ''
  form.source = ''
}

function applyItem(item) {
  form.id = item.id ?? ''
  form.name = item.name ?? ''
  form.description = item.description ?? ''
  form.tags = Array.isArray(item.tags) ? [...item.tags] : []
  form.content = item.content ?? ''
  form.source = item.source ?? ''
}

// ── load list ─────────────────────────────────────────────────────────────────
async function loadList() {
  loading.value = true
  try {
    const res = await listSkills()
    skills.value = res.items ?? []
  } catch {
    // error already shown by http interceptor
  } finally {
    loading.value = false
  }
}

onMounted(loadList)

// ── select a skill ────────────────────────────────────────────────────────────
async function selectSkill(skill) {
  if (activeId.value === skill.id && !isNew.value) return
  isNew.value = false
  activeId.value = skill.id
  loading.value = true
  try {
    const res = await getSkill(skill.id)
    applyItem(res.item)
  } catch {
    // fallback to list data
    applyItem(skill)
  } finally {
    loading.value = false
  }
}

// ── new skill ─────────────────────────────────────────────────────────────────
function startNew() {
  isNew.value = true
  activeId.value = null
  resetForm()
}

// ── save ──────────────────────────────────────────────────────────────────────
async function save() {
  if (!form.name.trim()) {
    message.warning('技能名称不能为空')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      tags: form.tags,
      content: form.content,
    }
    let item
    if (isNew.value) {
      const res = await createSkill(payload)
      item = res.item
      message.success('技能已创建')
    } else {
      const res = await updateSkill(activeId.value, payload)
      item = res.item
      message.success('技能已保存')
    }
    applyItem(item)
    isNew.value = false
    activeId.value = item.id
    await loadList()
  } catch {
    // handled by interceptor
  } finally {
    saving.value = false
  }
}

// ── delete ────────────────────────────────────────────────────────────────────
async function confirmDelete() {
  if (!activeId.value) return
  deleting.value = true
  try {
    await deleteSkill(activeId.value)
    message.success('技能已删除')
    resetForm()
    isNew.value = false
    activeId.value = null
    await loadList()
  } catch {
    // handled by interceptor
  } finally {
    deleting.value = false
  }
}

// ── computed: has selection ───────────────────────────────────────────────────
const hasSelection = computed(() => isNew.value || activeId.value !== null)

const tagColor = (tag) => {
  const palette = ['blue', 'cyan', 'green', 'purple', 'orange', 'geekblue', 'magenta']
  let h = 0
  for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) & 0xffffff
  return palette[Math.abs(h) % palette.length]
}
</script>

<template>
  <div class="skills-workspace">
    <!-- ── left panel: skill list ── -->
    <aside class="skills-sidebar">
      <div class="skills-sidebar-head">
        <h2>技能库</h2>
        <a-button type="primary" size="small" @click="startNew">
          <template #icon><PlusOutlined /></template>
          新建技能
        </a-button>
      </div>

      <div class="skills-list-scroll">
        <!-- loading skeleton -->
        <template v-if="loading && skills.length === 0">
          <div v-for="n in 4" :key="n" class="skill-card skill-card--skeleton">
            <a-skeleton active :paragraph="{ rows: 1 }" />
          </div>
        </template>

        <!-- empty state -->
        <div v-else-if="!loading && skills.length === 0 && !isNew" class="skills-empty">
          <BookOutlined class="skills-empty-icon" />
          <p>还没有技能</p>
          <a-button type="primary" @click="startNew">创建第一个技能</a-button>
        </div>

        <!-- new skill placeholder in list -->
        <div
          v-if="isNew"
          class="skill-card skill-card--active"
        >
          <strong class="skill-card-name">新技能</strong>
          <span class="skill-card-desc muted">未保存</span>
        </div>

        <!-- skill items -->
        <div
          v-for="skill in skills"
          :key="skill.id"
          class="skill-card"
          :class="{ 'skill-card--active': activeId === skill.id && !isNew }"
          @click="selectSkill(skill)"
        >
          <strong class="skill-card-name">{{ skill.name }}</strong>
          <span v-if="skill.description" class="skill-card-desc muted">{{ skill.description }}</span>
          <div v-if="skill.tags && skill.tags.length" class="skill-card-tags">
            <a-tag
              v-for="tag in skill.tags.slice(0, 4)"
              :key="tag"
              :color="tagColor(tag)"
              class="skill-tag"
            >{{ tag }}</a-tag>
          </div>
        </div>
      </div>
    </aside>

    <!-- ── right panel: editor ── -->
    <main class="skills-editor">
      <div v-if="!hasSelection" class="skills-placeholder">
        <FileTextOutlined class="skills-placeholder-icon" />
        <p>从左侧选择一个技能进行编辑，或点击「新建技能」</p>
      </div>

      <template v-else>
        <div class="skills-editor-head">
          <div class="skills-editor-title">
            <h2>{{ isNew ? '新建技能' : form.name || '编辑技能' }}</h2>
            <span v-if="!isNew && form.id" class="skill-id-badge">
              <code>{{ form.id }}</code>
            </span>
          </div>
          <a-space>
            <a-button
              type="primary"
              :loading="saving"
              @click="save"
            >
              <template #icon><SaveOutlined /></template>
              保存
            </a-button>
            <a-popconfirm
              v-if="!isNew"
              title="确认删除这个技能？此操作不可恢复。"
              ok-text="删除"
              cancel-text="取消"
              ok-type="danger"
              @confirm="confirmDelete"
            >
              <a-button danger :loading="deleting">
                <template #icon><DeleteOutlined /></template>
                删除
              </a-button>
            </a-popconfirm>
          </a-space>
        </div>

        <div class="skills-form">
          <a-spin :spinning="loading">
            <div class="form-grid">
              <!-- name -->
              <div class="form-field">
                <label class="form-label">技能名称 <span class="form-required">*</span></label>
                <a-input
                  v-model:value="form.name"
                  placeholder="如: send_email、search_web"
                  size="large"
                  allow-clear
                />
              </div>

              <!-- description -->
              <div class="form-field">
                <label class="form-label">描述</label>
                <a-input
                  v-model:value="form.description"
                  placeholder="简短描述这个技能的用途"
                  size="large"
                  allow-clear
                />
              </div>

              <!-- tags -->
              <div class="form-field">
                <label class="form-label">
                  <TagsOutlined style="margin-right:4px" />标签
                </label>
                <a-select
                  v-model:value="form.tags"
                  mode="tags"
                  placeholder="输入标签后按回车添加"
                  size="large"
                  style="width:100%"
                  :token-separators="[',']"
                />
              </div>

              <!-- content -->
              <div class="form-field form-field--full">
                <label class="form-label">
                  <FileTextOutlined style="margin-right:4px" />技能内容
                  <span class="form-hint">（支持 Markdown / 提示词正文）</span>
                </label>
                <a-textarea
                  v-model:value="form.content"
                  placeholder="在这里编写技能的 Markdown 内容或提示词..."
                  :auto-size="false"
                  class="skills-content-editor"
                />
              </div>

              <!-- source: read-only if present -->
              <div v-if="form.source" class="form-field">
                <label class="form-label">来源</label>
                <a-input :value="form.source" disabled />
              </div>
            </div>
          </a-spin>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
/* ── layout ── */
.skills-workspace {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  height: calc(100vh - 66px);
  overflow: hidden;
}

/* ── sidebar ── */
.skills-sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.70), rgba(255, 255, 255, 0.48)),
    radial-gradient(circle at 20% 4%, rgba(139, 92, 246, 0.12), transparent 28%);
  border-right: 1px solid rgba(255, 255, 255, 0.62);
  backdrop-filter: blur(20px);
}

.skills-sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: 0 0 auto;
  gap: 12px;
  padding: 16px 16px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.62);
}

.skills-sidebar-head h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 800;
  color: var(--text);
}

.skills-sidebar-head .ant-btn-primary {
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  border: 0;
  box-shadow: 0 8px 18px rgba(53, 120, 255, 0.20);
}

.skills-list-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 12px;
  display: grid;
  align-content: start;
  gap: 8px;
  scrollbar-width: none;
}

.skills-list-scroll::-webkit-scrollbar {
  display: none;
}

/* ── skill card ── */
.skill-card {
  padding: 12px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.56);
  border-radius: var(--radius-md);
  box-shadow: 0 6px 16px rgba(27, 39, 66, 0.04);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    background 0.18s ease;
  display: grid;
  gap: 4px;
}

.skill-card:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 12px 28px rgba(27, 39, 66, 0.08);
}

.skill-card--active {
  background:
    linear-gradient(135deg, rgba(139, 92, 246, 0.14), rgba(53, 120, 255, 0.10)),
    rgba(255, 255, 255, 0.88);
  border-color: rgba(139, 92, 246, 0.26);
  box-shadow: 0 12px 28px rgba(91, 77, 190, 0.10);
}

.skill-card-name {
  display: block;
  color: var(--text);
  font-weight: 760;
  font-size: 13.5px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.skill-card-desc {
  display: block;
  font-size: 12px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.skill-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 4px;
}

.skill-tag {
  font-size: 11px;
  border-radius: 999px;
  margin: 0;
  padding: 0 7px;
  line-height: 18px;
}

/* ── skeleton ── */
.skill-card--skeleton {
  cursor: default;
  pointer-events: none;
  min-height: 64px;
}

/* ── empty state ── */
.skills-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 16px;
  text-align: center;
  color: var(--muted);
}

.skills-empty-icon {
  font-size: 36px;
  color: rgba(139, 92, 246, 0.36);
}

.skills-empty p {
  margin: 0;
  font-size: 13px;
}

/* ── editor panel ── */
.skills-editor {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  padding: 24px;
  background:
    radial-gradient(circle at 80% 10%, rgba(139, 92, 246, 0.07), transparent 30%),
    radial-gradient(circle at 10% 90%, rgba(53, 120, 255, 0.06), transparent 28%);
}

.skills-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  color: var(--muted);
  text-align: center;
}

.skills-placeholder-icon {
  font-size: 52px;
  color: rgba(53, 120, 255, 0.22);
}

.skills-placeholder p {
  margin: 0;
  font-size: 14px;
  max-width: 280px;
}

/* ── editor head ── */
.skills-editor-head {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.skills-editor-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.skills-editor-title h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: var(--text);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.skill-id-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  background: rgba(139, 92, 246, 0.08);
  border: 1px solid rgba(139, 92, 246, 0.16);
  border-radius: 999px;
  font-size: 11.5px;
  color: #5b21b6;
  white-space: nowrap;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-id-badge code {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 11px;
}

/* ── form ── */
.skills-form {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  scrollbar-width: none;
}

.skills-form::-webkit-scrollbar {
  display: none;
}

.form-grid {
  display: grid;
  gap: 18px;
}

.form-field {
  display: grid;
  gap: 6px;
}

.form-field--full {
  /* content editor takes the rest of available height */
}

.form-label {
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
  color: var(--muted);
  letter-spacing: 0.03em;
}

.form-required {
  color: #e02424;
  margin-left: 2px;
}

.form-hint {
  font-size: 11px;
  font-weight: 500;
  text-transform: none;
  color: var(--muted);
  opacity: 0.78;
  letter-spacing: 0;
  margin-left: 4px;
}

/* monospace content editor */
.skills-content-editor {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono', Menlo, monospace !important;
  font-size: 13px !important;
  line-height: 1.7 !important;
  min-height: 340px;
  resize: vertical;
  background: rgba(14, 20, 38, 0.03);
  border-color: rgba(139, 92, 246, 0.16);
}

.skills-content-editor:hover {
  border-color: rgba(139, 92, 246, 0.38);
}

.skills-content-editor:focus {
  border-color: rgba(139, 92, 246, 0.56);
  box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.10);
}

.muted {
  color: var(--muted);
}

/* ── responsive ── */
@media (max-width: 760px) {
  .skills-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: calc(100vh - 110px);
    overflow: visible;
  }

  .skills-sidebar {
    height: min(400px, 50vh);
    border-right: 0;
    border-bottom: 1px solid rgba(255, 255, 255, 0.62);
  }

  .skills-editor {
    min-height: 500px;
  }
}
</style>
