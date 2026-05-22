<script setup>
import { CloudUploadOutlined } from '@ant-design/icons-vue'
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <span class="eyebrow">File Upload</span>
        <h1>通用文件上传</h1>
      </div>
    </div>
    <a-card class="panel-card upload-placeholder" :bordered="false">
      <a-alert
        type="info"
        show-icon
        message="后端暂无通用文件上传接口"
        description="当前可用上传能力是工具声明与源码上传：POST /api/tools/upload。通用文件上传页面先保留为前端占位。"
      />
      <a-upload-dragger disabled class="mt-24">
        <p class="ant-upload-drag-icon"><CloudUploadOutlined /></p>
        <p class="ant-upload-text">接口接入后可在此上传文件</p>
        <p class="ant-upload-hint">当前按钮禁用，不会发起网络请求。</p>
      </a-upload-dragger>
    </a-card>
  </section>
</template>
