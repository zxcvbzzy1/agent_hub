export function questionAnswers(questions, responses) {
  return questions.map(question => {
    const response = responses[question.id] || {}
    const selected = question.type === 'single'
      ? (response.selected ? [response.selected] : []) : (response.selected || [])
    const text = (response.text || '').trim()
    if (question.type === 'text' ? !text : !selected.length) throw new Error('请回答全部问题')
    if (selected.includes('other') && !text) throw new Error('请填写“其他”的内容')
    return { question_id: question.id, selected_option_ids: selected,
      text: question.type === 'text' || selected.includes('other') ? text : '' }
  })
}
