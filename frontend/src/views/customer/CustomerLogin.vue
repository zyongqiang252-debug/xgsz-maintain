<template>
  <div class="c-page">
    <div class="c-card">
      <div class="c-brand">
        <img src="/logo-icon.png" alt="芯光智数" class="c-logo" />
        <h1>芯光智数</h1>
        <p>客户报修中心</p>
      </div>
      <el-form @submit.prevent>
        <el-form-item>
          <el-input v-model="phone" size="large" placeholder="手机号" maxlength="20" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" size="large" type="password" show-password
                    placeholder="密码" @keyup.enter="login" />
        </el-form-item>
        <el-button class="c-btn" type="primary" size="large" :loading="loading" @click="login">
          登 录
        </el-button>
      </el-form>
      <p class="c-hint">账号由服务方开通，忘记密码请联系管理员</p>
      <p class="c-staff"><a @click.prevent="goStaffLogin">内部员工登录 →</a></p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import customerRequest from '../../api/customer'

const router = useRouter()
const phone = ref('')
const password = ref('')
const loading = ref(false)

const goStaffLogin = () => { window.location.href = '/login' }

// 只有 token 仍然有效才直接进门户；否则清掉残留 token，正常显示登录表单
// （旧逻辑只看「有没有 token」，过期 token 会让人在 /c 与 /c/login 之间来回跳，看着像登不上）
onMounted(async () => {
  if (!localStorage.getItem('customer_token')) return
  try {
    await customerRequest.get('/customer/sites')
    router.replace('/c')
  } catch {
    localStorage.removeItem('customer_token')
    localStorage.removeItem('customer_user')
  }
})

const login = async () => {
  if (!phone.value || !password.value) {
    ElMessage.warning('请输入手机号和密码')
    return
  }
  loading.value = true
  try {
    const res = await customerRequest.post('/customer/login', {
      phone: phone.value.trim(), password: password.value,
    })
    localStorage.setItem('customer_token', res.token)
    localStorage.setItem('customer_user', JSON.stringify(res.customer))
    ElMessage.success(`欢迎，${res.customer.name}`)
    router.replace('/c')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.c-page { min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #E6FAF7 0%, #E8F4FF 50%, #F0E6FF 100%); padding: 20px; }
.c-card { width: 400px; max-width: 100%; background: #fff; border-radius: 16px;
  padding: 40px 36px 28px; box-shadow: 0 12px 40px rgba(15, 198, 194, .18); }
.c-brand { text-align: center; margin-bottom: 26px; }
.c-logo { width: 64px; height: 64px; object-fit: contain; }
.c-brand h1 { margin: 10px 0 4px; font-size: 26px; color: #1D2129; letter-spacing: 1px; }
.c-brand p { margin: 0; color: #86909C; font-size: 14px; }
.c-btn { width: 100%; margin-top: 4px; }
.c-hint { margin: 18px 0 0; text-align: center; font-size: 12px; color: #C9CDD4; }
.c-staff { margin: 10px 0 0; text-align: center; font-size: 12px; }
.c-staff a { color: #86909C; cursor: pointer; text-decoration: none; }
.c-staff a:hover { color: #0FC6C2; text-decoration: underline; }
</style>
