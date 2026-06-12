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
const skillCountLabel = computed(() => `${skills.value.length} 个技能`)
const editorModeLabel = computed(() => (isNew.value ? '新建草稿' : '正在编辑'))
const editorDescription = computed(() => (
  isNew.value
    ? '创建一个可复用的 Agent 能力单元'
    : form.description || '维护技能的名称、标签与提示词正文'
))

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
        <div>
          <span class="skills-sidebar-kicker">SKILLS</span>
          <h2>技能库</h2>
        </div>
        <span class="skills-count">{{ skillCountLabel }}</span>
        <a-button type="primary" class="skills-new-button" @click="startNew">
          <template #icon><PlusOutlined /></template>
          新建
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
          class="skill-card skill-card--active skill-card--new"
        >
          <div class="skill-card-new-icon"><PlusOutlined /></div>
          <div>
            <strong class="skill-card-name">新建技能</strong>
            <span class="skill-card-desc muted">未保存草稿</span>
          </div>
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
            <div class="skills-title-icon">
              <PlusOutlined v-if="isNew" />
              <BookOutlined v-else />
            </div>
            <div class="skills-title-copy">
              <div class="skills-editor-kicker">
                <span class="status-dot"></span>
                {{ editorModeLabel }}
              </div>
              <h2>{{ isNew ? '新建技能' : form.name || '编辑技能' }}</h2>
              <p>{{ editorDescription }}</p>
            </div>
          </div>
          <a-space>
            <a-button
              type="primary"
              class="skills-save-button"
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
          <div class="skills-form-panel">
            <div class="form-panel-head">
              <div class="form-panel-title">
                <FileTextOutlined />
                <div>
                  <strong>{{ isNew ? '基础信息' : '技能配置' }}</strong>
                  <span v-if="!isNew && form.id" class="skill-id-badge">
                    <code>{{ form.id }}</code>
                  </span>
                </div>
              </div>
              <span class="form-panel-chip">{{ isNew ? 'Draft' : 'Saved Skill' }}</span>
            </div>

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
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
/* ── layout ── */
.skills-workspace {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
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
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  flex: 0 0 auto;
  gap: 12px;
  padding: 18px 16px 14px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.76), rgba(245, 250, 255, 0.48)),
    rgba(255, 255, 255, 0.35);
  border-bottom: 1px solid rgba(255, 255, 255, 0.62);
}

.skills-sidebar-kicker {
  display: block;
  margin-bottom: 2px;
  color: var(--accent);
  font-size: 10px;
  font-weight: 850;
  letter-spacing: 0.08em;
}

.skills-sidebar-head h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 800;
  color: var(--text);
}

.skills-count {
  justify-self: end;
  padding: 4px 9px;
  color: #175199;
  background: rgba(255, 255, 255, 0.66);
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 999px;
  box-shadow: 0 8px 20px rgba(27, 39, 66, 0.05);
  font-size: 12px;
  font-weight: 750;
}

.skills-new-button {
  grid-column: 1 / -1;
  height: 36px;
  border-radius: 10px;
}

.skills-sidebar-head .ant-btn-primary,
.skills-save-button {
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
  position: relative;
  padding: 13px;
  background: rgba(255, 255, 255, 0.58);
  border: 1px solid rgba(255, 255, 255, 0.56);
  border-radius: 12px;
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
    linear-gradient(135deg, rgba(53, 120, 255, 0.16), rgba(24, 198, 212, 0.12)),
    rgba(255, 255, 255, 0.88);
  border-color: rgba(53, 120, 255, 0.24);
  box-shadow: 0 12px 28px rgba(53, 120, 255, 0.10);
}

.skill-card--active::before {
  position: absolute;
  top: 12px;
  bottom: 12px;
  left: 0;
  width: 3px;
  content: "";
  background: linear-gradient(180deg, var(--accent), var(--accent-2));
  border-radius: 999px;
}

.skill-card--new {
  grid-template-columns: 34px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.skill-card-new-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  border-radius: 10px;
  box-shadow: 0 10px 22px rgba(53, 120, 255, 0.20);
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
  padding: 22px 24px 24px;
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
  margin-bottom: 16px;
  padding: 16px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.80), rgba(246, 250, 255, 0.58)),
    rgba(255, 255, 255, 0.42);
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 16px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.88),
    0 14px 34px rgba(27, 39, 66, 0.08);
  backdrop-filter: blur(18px) saturate(1.16);
  -webkit-backdrop-filter: blur(18px) saturate(1.16);
}

.skills-editor-title {
  display: flex;
  align-items: center;
  gap: 13px;
  min-width: 0;
}

.skills-title-icon {
  display: grid;
  flex: 0 0 auto;
  place-items: center;
  width: 44px;
  height: 44px;
  color: #fff;
  background: linear-gradient(135deg, var(--accent), var(--accent-2) 58%, var(--accent-5));
  border-radius: 13px;
  box-shadow: 0 14px 30px rgba(53, 120, 255, 0.22);
  font-size: 18px;
}

.skills-title-copy {
  min-width: 0;
}

.skills-editor-kicker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 850;
}

.status-dot {
  width: 7px;
  height: 7px;
  background: linear-gradient(135deg, var(--accent-3), var(--accent-2));
  border-radius: 999px;
  box-shadow: 0 0 0 3px rgba(88, 214, 141, 0.16);
}

.skills-editor-title h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: var(--text);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.skills-editor-title p {
  max-width: 620px;
  margin: 3px 0 0;
  color: var(--muted);
  font-size: 13px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.skill-id-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 9px;
  background: rgba(53, 120, 255, 0.08);
  border: 1px solid rgba(53, 120, 255, 0.14);
  border-radius: 999px;
  font-size: 11.5px;
  color: #175199;
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
  padding-bottom: 4px;
  scrollbar-width: none;
}

.skills-form::-webkit-scrollbar {
  display: none;
}

.skills-form-panel {
  min-height: 100%;
  padding: 18px;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.82), rgba(250, 252, 255, 0.66)),
    rgba(255, 255, 255, 0.48);
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 18px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.88),
    0 18px 46px rgba(27, 39, 66, 0.09);
  backdrop-filter: blur(20px) saturate(1.12);
  -webkit-backdrop-filter: blur(20px) saturate(1.12);
}

.form-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(95, 111, 139, 0.12);
}

.form-panel-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  color: var(--accent);
}

.form-panel-title strong {
  display: block;
  color: var(--text);
  font-size: 15px;
  font-weight: 800;
}

.form-panel-title div {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.form-panel-chip {
  flex: 0 0 auto;
  padding: 5px 10px;
  color: #087681;
  background: rgba(234, 255, 244, 0.78);
  border: 1px solid rgba(88, 214, 141, 0.20);
  border-radius: 999px;
  font-size: 12px;
  font-weight: 780;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px 16px;
}

.form-field {
  display: grid;
  gap: 6px;
}

.form-field--full {
  grid-column: 1 / -1;
}

.form-label {
  font-size: 12px;
  font-weight: 800;
  color: var(--muted);
  letter-spacing: 0;
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
  min-height: 360px;
  resize: vertical;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(246, 250, 255, 0.66)),
    rgba(14, 20, 38, 0.025);
  border-color: rgba(53, 120, 255, 0.16);
  border-radius: 12px;
}

.skills-content-editor:hover {
  border-color: rgba(53, 120, 255, 0.38);
}

.skills-content-editor:focus {
  border-color: rgba(53, 120, 255, 0.56);
  box-shadow: 0 0 0 3px rgba(53, 120, 255, 0.10);
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
    padding: 18px;
  }

  .skills-editor-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .skills-editor-title p {
    white-space: normal;
  }

  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
