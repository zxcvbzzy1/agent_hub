<script setup>
import { computed, nextTick, reactive, ref, useId, watch } from 'vue'
import { message as notice } from 'ant-design-vue'
import { CheckOutlined, LeftOutlined, RightOutlined, PaperClipOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import ChatAttachments from './ChatAttachments.vue'
import { useChatFiles } from '@/composables/useChatFiles'
import { questionAnswers } from '@/utils/humanQuestions'

const props = defineProps({ question: { type: Object, required: true }, canAnswer: Boolean,
  submit: { type: Function, required: true } })
const responses = reactive({})
const sending = ref(false)
const activeIndex = ref(0)
const attachmentsOpen = ref(false)
const cardId = useId()
const tabRefs = ref([])
const questions = computed(() => props.question.questions || [])
const activeQuestion = computed(() => questions.value[activeIndex.value])
const lastQuestion = computed(() => activeIndex.value === questions.value.length - 1)
const targetKey = computed(() => `question:${props.question.confirmation_id}`)
const files = useChatFiles(targetKey)
const draft = files.draft
const editable = computed(() => props.question.status === 'pending' && props.canAnswer)
const disabled = computed(() => !editable.value || sending.value)
const statusLabel = computed(() => props.question.status === 'pending' ? '等待回答'
  : props.question.status === 'resolved' ? '已回答' : '已取消')
const answeredCount = computed(() => questions.value.filter(isAnswered).length)
const progress = computed(() => questions.value.length ? answeredCount.value / questions.value.length * 100 : 0)
const typeLabels = { single: '单选', multiple: '多选', text: '文字回答' }
watch(() => props.question.confirmation_id, () => {
  activeIndex.value = 0
  attachmentsOpen.value = false
  for (const key of Object.keys(responses)) delete responses[key]
  for (const question of props.question.questions || []) {
    responses[question.id] = { selected: question.type === 'single' ? '' : [], text: '' }
  }
}, { immediate: true })
function otherSelected(question) {
  const selected = responses[question.id]?.selected
  return selected === 'other' || (Array.isArray(selected) && selected.includes('other'))
}
function savedAnswer(id) { return props.question.answer?.answers?.find(answer => answer.question_id === id) }
function isAnswered(question) {
  if (props.question.status !== 'pending') return Boolean(savedAnswer(question.id))
  try { questionAnswers([question], responses); return true }
  catch { return false }
}
function switchQuestion(index, focus = false) {
  if (sending.value || !questions.value.length) return
  activeIndex.value = Math.max(0, Math.min(index, questions.value.length - 1))
  if (focus) nextTick(() => tabRefs.value[activeIndex.value]?.focus())
}
function navigateTabs(event) {
  const target = { ArrowLeft: activeIndex.value - 1, ArrowRight: activeIndex.value + 1,
    Home: 0, End: questions.value.length - 1 }[event.key]
  if (target === undefined) return
  event.preventDefault()
  switchQuestion(target, true)
}
async function submit() {
  if (disabled.value || files.busy.value) return
  let answers
  try { answers = questionAnswers(props.question.questions, responses) }
  catch (error) {
    switchQuestion(questions.value.findIndex(question => !isAnswered(question)), true)
    notice.warning(error.message)
    return
  }
  sending.value = true
  try {
    await props.submit({ answers, file_ids: draft.value.items.map(item => item.file.file_id) })
  } catch { /* The HTTP interceptor displays the error; retain the draft for retry. */ }
  finally { sending.value = false }
}
</script>

<template>
  <section class="human-question-card" :class="{ 'is-resolved': question.status === 'resolved' }">
    <header class="question-heading">
      <div class="question-heading-title">
        <span class="question-heading-icon"><CheckOutlined v-if="question.status === 'resolved'" /><QuestionCircleOutlined v-else /></span>
        <div><strong>需要你确认</strong><span class="question-subtitle">{{ question.status === 'pending' ? '补充一点信息，我们继续' : '本次提问记录' }}</span></div>
      </div>
      <span class="question-status" :class="question.status"><span class="status-dot"></span>{{ statusLabel }}</span>
    </header>

    <div v-if="questions.length > 1" class="question-tabs" role="tablist" aria-label="选择问题" @keydown="navigateTabs">
      <button v-for="(q, index) in questions" :id="`${cardId}-tab-${index}`" :key="q.id"
        :ref="element => { tabRefs[index] = element }" type="button" role="tab"
        :aria-selected="index === activeIndex" :aria-controls="`${cardId}-panel`"
        :tabindex="index === activeIndex ? 0 : -1" :disabled="sending"
        :class="{ active: index === activeIndex, answered: isAnswered(q) }"
        :title="q.question" @click="switchQuestion(index)">
        <span class="tab-number"><CheckOutlined v-if="isAnswered(q)" /><template v-else>{{ index + 1 }}</template></span>
        <span class="tab-label">问题 {{ index + 1 }}</span>
      </button>
    </div>

    <div v-if="activeQuestion" :id="`${cardId}-panel`" class="question-panel"
      :role="questions.length > 1 ? 'tabpanel' : undefined"
      :aria-labelledby="questions.length > 1 ? `${cardId}-tab-${activeIndex}` : undefined">
      <div class="question-eyebrow"><span>{{ typeLabels[activeQuestion.type] }}</span><span>{{ activeIndex + 1 }} / {{ questions.length }}</span></div>
      <h3>{{ activeQuestion.question }}</h3>
      <template v-if="question.status === 'pending'">
        <p class="question-hint">{{ activeQuestion.type === 'multiple' ? '可选择多项，也可以补充其他想法' : activeQuestion.type === 'single' ? '选择最符合你想法的一项' : '写下你的想法或具体要求' }}</p>
        <a-radio-group v-if="activeQuestion.type === 'single'" :key="activeQuestion.id"
          v-model:value="responses[activeQuestion.id].selected" :disabled="disabled" class="question-options">
          <a-radio v-for="(option, index) in activeQuestion.options" :key="option.id" :value="option.id" class="question-option"
            :class="{ selected: responses[activeQuestion.id].selected === option.id }">
            <span class="option-content"><span class="option-letter" aria-hidden="true">{{ option.id === 'other' ? '+' : String.fromCharCode(65 + index) }}</span><span>{{ option.label }}</span></span>
          </a-radio>
        </a-radio-group>
        <a-checkbox-group v-else-if="activeQuestion.type === 'multiple'" :key="activeQuestion.id"
          v-model:value="responses[activeQuestion.id].selected" :disabled="disabled" class="question-options">
          <a-checkbox v-for="(option, index) in activeQuestion.options" :key="option.id" :value="option.id" class="question-option"
            :class="{ selected: responses[activeQuestion.id].selected.includes(option.id) }">
            <span class="option-content"><span class="option-letter" aria-hidden="true">{{ option.id === 'other' ? '+' : String.fromCharCode(65 + index) }}</span><span>{{ option.label }}</span></span>
          </a-checkbox>
        </a-checkbox-group>
        <a-textarea v-if="activeQuestion.type === 'text' || otherSelected(activeQuestion)" :key="activeQuestion.id + '-text'"
          v-model:value="responses[activeQuestion.id].text" class="question-textarea"
          :disabled="disabled" :rows="3" :placeholder="activeQuestion.type === 'text' ? '填写回答' : '填写其他选项'" />
      </template>
      <div v-else-if="savedAnswer(activeQuestion.id)" class="saved-answer">
        <CheckOutlined /><span>{{ [...savedAnswer(activeQuestion.id).selected_options, savedAnswer(activeQuestion.id).text].filter(Boolean).join('；') }}</span>
      </div>
      <p v-else class="question-hint">{{ question.reason || '本次提问已结束' }}</p>
    </div>

    <div v-if="editable" class="question-attachments">
      <button type="button" class="attachments-toggle" :disabled="sending" :aria-expanded="attachmentsOpen"
        :aria-controls="`${cardId}-attachments`" @click="attachmentsOpen = !attachmentsOpen">
        <span><PaperClipOutlined /> {{ draft.items.length ? `附件（${draft.items.length}）` : '补充附件' }}<small>可选</small></span>
        <RightOutlined :rotate="attachmentsOpen ? 90 : 0" />
      </button>
      <div v-show="attachmentsOpen" :id="`${cardId}-attachments`" class="attachments-body">
        <ChatAttachments :items="draft.items" :target-key="targetKey" :disabled="disabled" :active="attachmentsOpen"
          @upload="files.uploadFiles" @reuse="files.addExisting" @remove="files.removeItem" @retry="files.retry" />
      </div>
    </div>

    <footer class="question-footer">
      <div class="answer-progress" aria-live="polite"><span>{{ answeredCount }} / {{ questions.length }} 已答</span>
        <div class="progress-track" aria-hidden="true"><span :style="{ width: `${progress}%` }"></span></div>
      </div>
      <div class="question-navigation">
        <a-button v-if="questions.length > 1" class="previous-question" :disabled="activeIndex === 0 || sending" @click="switchQuestion(activeIndex - 1)"><LeftOutlined /><span>上一题</span></a-button>
        <a-button v-if="!lastQuestion" type="primary" :disabled="sending" @click="switchQuestion(activeIndex + 1)">下一题<RightOutlined /></a-button>
        <a-button v-else-if="editable" type="primary" :loading="sending" :disabled="disabled || files.busy.value" @click="submit">提交全部答案<CheckOutlined v-if="!sending" /></a-button>
      </div>
    </footer>
    <p v-if="question.status === 'pending' && !canAnswer" class="question-note">等待本次任务的发起人回答</p>
    <p v-else-if="editable && files.busy.value" class="question-note">提交前请完成附件上传，或移除上传失败的文件</p>
  </section>
</template>

<style scoped>
.human-question-card { width: 540px; max-width: 100%; min-width: min(260px, 100%); overflow: hidden; color: var(--text, #142033); background: var(--panel-solid, #fff); border: 1px solid var(--line, #e4e9f2); border-radius: 16px; box-shadow: 0 6px 24px rgba(27, 39, 66, .04); }
.question-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 18px 20px; background: linear-gradient(120deg, var(--accent-soft, #eaf3ff), #fff 85%); }
.question-heading-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
.question-heading-icon { display: grid; place-items: center; flex-shrink: 0; width: 36px; height: 36px; border-radius: 11px; color: var(--accent, #3578ff); background: #fff; font-size: 19px; box-shadow: 0 2px 8px rgba(53, 120, 255, .08); }
.question-heading strong { font-size: 14px; }
.question-subtitle { display: block; margin-top: 3px; font-size: 11px; color: var(--muted, #667085); }
.question-status { display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0; font-size: 11px; color: var(--muted, #667085); }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: #98a2b3; }
.pending .status-dot { background: var(--accent, #3578ff); }
.resolved { color: var(--success, #16a36a); }
.resolved .status-dot { background: currentColor; }
.question-tabs { display: flex; gap: 6px; padding: 12px 20px 0; }
.question-tabs button { display: flex; align-items: center; justify-content: center; gap: 8px; flex: 1; padding: 10px 6px; border: 1px solid transparent; border-radius: 9px; background: #f7f9fc; color: var(--muted, #667085); font: inherit; font-size: 12px; cursor: pointer; transition: background .16s, border-color .16s, color .16s; }
.question-tabs button:hover { background: #edf2fa; }
.question-tabs button.active { background: var(--accent-soft, #eaf3ff); color: var(--accent, #3578ff); border-color: rgba(53, 120, 255, .22); font-weight: 600; }
.tab-number { display: grid; place-items: center; width: 20px; height: 20px; border-radius: 6px; background: #e9edf4; font-size: 10px; }
.active .tab-number { background: var(--accent, #3578ff); color: #fff; }
.answered:not(.active) .tab-number { color: var(--success, #16a36a); background: var(--mint-soft, #eafff4); }
.question-panel { padding: 20px; }
.question-eyebrow { display: flex; align-items: center; justify-content: space-between; color: var(--muted, #667085); font-size: 11px; }
.question-eyebrow > span:first-child { color: var(--accent, #3578ff); font-weight: 500; }
.question-panel h3 { margin: 10px 0 6px; font-size: 16px; line-height: 1.6; font-weight: 600; white-space: pre-wrap; overflow-wrap: anywhere; }
.question-hint { margin: 0 0 16px; color: var(--muted, #667085); font-size: 12px; line-height: 1.6; }
.question-options { display: flex; flex-direction: column; gap: 8px; width: 100%; }
.question-options :deep(.question-option) { display: flex; align-items: center; gap: 8px; width: 100%; margin: 0; padding: 11px 12px; border: 1px solid var(--line, #e4e9f2); border-radius: 10px; background: #fff; transition: border-color .16s, background .16s; }
.question-options :deep(.question-option:hover) { border-color: #9abaff; background: #fafcff; }
.question-options :deep(.question-option.selected) { border-color: var(--accent, #3578ff); background: var(--accent-soft, #eaf3ff); }
.question-options :deep(.ant-radio), .question-options :deep(.ant-checkbox) { top: 0; }
.question-options :deep(.ant-radio + span), .question-options :deep(.ant-checkbox + span) { flex: 1; min-width: 0; padding: 0; }
.option-content { display: flex; align-items: center; gap: 10px; line-height: 1.5; overflow-wrap: anywhere; }
.option-letter { display: grid; place-items: center; width: 23px; height: 23px; flex-shrink: 0; background: #f3f5f9; border-radius: 6px; color: var(--muted, #667085); font-size: 11px; }
.selected .option-letter { color: var(--accent, #3578ff); background: #fff; }
.question-textarea { margin-top: 10px; border-radius: 10px; padding: 10px 12px; font-size: 13px; }
.saved-answer { display: flex; align-items: flex-start; gap: 8px; margin-top: 14px; padding: 12px; border: 1px solid #d6eee3; border-radius: 10px; color: #227250; background: #f4fbf7; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.7; }
.saved-answer > :first-child { margin-top: 4px; }
.question-attachments { margin: 0 20px; border-top: 1px solid var(--line, #e4e9f2); }
.attachments-toggle { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 12px 0; border: 0; background: transparent; color: var(--muted, #667085); font: inherit; font-size: 12px; cursor: pointer; }
.attachments-toggle > span:first-child { display: flex; align-items: center; gap: 7px; }
.attachments-toggle small { margin-left: 2px; color: #98a2b3; font-size: 10px; }
.attachments-body :deep(.chat-attachments) { margin: 0 0 12px; }
.attachments-body :deep(.attachment-limit) { font-size: 10px; }
.question-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 20px; border-top: 1px solid var(--line, #e4e9f2); background: #fafbfd; }
.answer-progress { flex: 1; max-width: 100px; min-width: 46px; color: var(--muted, #667085); font-size: 11px; }
.progress-track { height: 3px; margin-top: 7px; background: #e8edf5; border-radius: 3px; overflow: hidden; }
.progress-track span { display: block; height: 100%; background: var(--accent, #3578ff); transition: width .2s; }
.question-navigation { display: flex; gap: 8px; flex-shrink: 0; }
.question-navigation :deep(.ant-btn) { display: inline-flex; align-items: center; justify-content: center; gap: 4px; border-radius: 8px; font-size: 12px; box-shadow: none; }
.question-note { margin: 0; padding: 0 20px 14px; background: #fafbfd; color: var(--muted, #667085); font-size: 11px; }
.question-tabs button:focus-visible, .attachments-toggle:focus-visible { outline: 2px solid var(--accent, #3578ff); outline-offset: 2px; }
.is-resolved .question-heading-icon { color: var(--success, #16a36a); }
@media (max-width: 480px) {
  .question-heading, .question-panel { padding: 14px; }
  .question-tabs { padding: 10px 14px 0; }
  .question-attachments { margin: 0 14px; }
  .question-footer { gap: 10px; padding: 12px 14px; }
  .question-panel h3 { font-size: 14px; }
  .question-navigation { gap: 6px; }
  .question-navigation :deep(.ant-btn) { padding-inline: 9px; }
  .question-note { padding-inline: 14px; }
}
</style>
