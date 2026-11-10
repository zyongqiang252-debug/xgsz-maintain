import axios from 'axios'

// 客户门户专用请求实例：只带 customer_token，避免和内部账号 token 混用
const customerRequest = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

customerRequest.interceptors.request.use((config) => {
  const token = localStorage.getItem('customer_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

customerRequest.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(error),
)

export default customerRequest
