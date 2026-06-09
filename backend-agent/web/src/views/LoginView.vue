<script setup>
import { reactive, ref } from 'vue'
import { Lock, User } from '@element-plus/icons-vue'

const emit = defineEmits(['login'])
const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
})

const formRef = ref(null)
const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  if (props.loading) return
  await formRef.value?.validate()
  emit('login', {
    username: form.username,
    password: form.password,
  })
}
</script>

<template>
  <main class="login-shell">
    <section class="login-panel">
      <div class="login-brand">
        <img class="login-brand__mark" src="/brand/wecom-agent-mark.svg" alt="数字员工" />
        <div>
          <p>Local Runtime</p>
          <h1>企微数字员工V1.0</h1>
        </div>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        class="login-form"
        label-position="top"
        @submit.prevent="submit"
      >
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :prefix-icon="User" autocomplete="username" size="large" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            :prefix-icon="Lock"
            autocomplete="current-password"
            size="large"
            type="password"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button class="login-submit" type="primary" size="large" :loading="loading" @click="submit">
          登录控制台
        </el-button>
      </el-form>
    </section>
  </main>
</template>
