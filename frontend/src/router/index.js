import { createRouter, createWebHistory } from 'vue-router'
import ChatView from '../views/ChatView.vue'

const routes = [
  { path: '/', name: 'chat', component: ChatView },
  // future: { path: '/node', component: NodeTopologyView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
