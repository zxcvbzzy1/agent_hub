import test from 'node:test'
import assert from 'node:assert/strict'
import { questionAnswers } from './humanQuestions.js'

const questions = [{ id: 'q1', type: 'single' }, { id: 'q2', type: 'multiple' }, { id: 'q3', type: 'text' }]
test('build structured answers with other and free text', () => {
  const result = questionAnswers(questions, {
    q1: { selected: 'o1' }, q2: { selected: ['o1', 'other'], text: ' extra ' }, q3: { text: ' answer ' },
  })
  assert.deepEqual(result[1], { question_id: 'q2', selected_option_ids: ['o1', 'other'], text: 'extra' })
  assert.equal(result[2].text, 'answer')
})
test('require every answer and nonempty other text', () => {
  assert.throws(() => questionAnswers(questions, {}), /全部问题/)
  assert.throws(() => questionAnswers(questions.slice(0, 1), { q1: { selected: 'other', text: ' ' } }), /其他/)
})
test('clearing other selection does not submit stale supplementary text', () => {
  assert.equal(questionAnswers(questions.slice(0, 1), { q1: { selected: 'o2', text: 'old other' } })[0].text, '')
})
