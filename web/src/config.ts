/** 开发时默认启用假接口;设置 VITE_USE_MOCK=false 可以关掉,改连真实后端。 */
export const USE_MOCK = import.meta.env.DEV && import.meta.env.VITE_USE_MOCK !== 'false'
