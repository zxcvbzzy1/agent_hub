<script setup>
import { reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import JsonBlock from '@/components/workflow/JsonBlock.vue'
import { useToolsStore } from '@/stores/tools'

const emit = defineEmits(['uploaded'])
const tools = useToolsStore()
const schemaText = ref('{\n  "type": "object",\n  "properties": {}\n}')
const metadataText = ref('{}')
const form = reactive({
  name: '',
  description: '',
  field: 'system',
  source_code: '',
})
const uploaded = ref(null)

function beforeUpload(file) {
  const reader = new FileReader()
  reader.onload = () => {
    form.source_code = reader.result
    message.success(`已读取 ${file.name}`)
  }
  reader.readAsText(file)
  return false
}

async function submit() {
  const payload = {
    ...form,
    input_schema: JSON.parse(schemaText.value || '{}'),
    metadata: JSON.parse(metadataText.value || '{}'),
  }
  uploaded.value = await tools.uploadTool(payload)
  message.success('工具已上传并注册')
  emit('uploaded', uploaded.value)
}
</script>

<template>
  <div class="two-column-grid wide-left">
    <a-card class="panel-card" title="工具声明" :bordered="false">
      <a-form layout="vertical" @finish="submit">
        <a-form-item label="工具名称" required>
          <a-input v-model:value="form.name" placeholder="my_tool" />
        </a-form-item>
        <a-form-item label="工具领域">
          <a-select v-model:value="form.field">
            <a-select-option value="system">system</a-select-option>
            <a-select-option value="write_agent">write_agent</a-select-option>
            <a-select-option value="human">human</a-select-option>
            <a-select-option value="memory">memory</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="说明">
          <a-textarea v-model:value="form.description" :rows="3" />
        </a-form-item>
        <a-form-item label="Input Schema JSON">
          <a-textarea v-model:value="schemaText" :rows="7" class="code-input" />
        </a-form-item>
        <a-form-item label="Metadata JSON">
          <a-textarea v-model:value="metadataText" :rows="4" class="code-input" />
        </a-form-item>
        <a-upload :before-upload="beforeUpload" :show-upload-list="false">
          <a-button>选择源码文件</a-button>
        </a-upload>
        <a-form-item label="Source Code">
          <a-textarea v-model:value="form.source_code" :rows="10" class="code-input" />
        </a-form-item>
        <a-button type="primary" html-type="submit" :loading="tools.loading">上传并注册</a-button>
      </a-form>
    </a-card>

    <a-card class="panel-card" title="上传结果" :bordered="false">
      <a-alert type="warning" show-icon message="当前后端不做源码审查或沙箱隔离，请只上传可信实现。" />
      <JsonBlock class="mt-16" :value="uploaded || { status: 'waiting' }" />
    </a-card>
  </div>
</template>
