const input = document.getElementById('base')
chrome.storage.sync.get('base').then(({ base }) => { input.value = base || 'http://localhost:8100' })
document.getElementById('save').addEventListener('click', async () => {
  await chrome.storage.sync.set({ base: input.value.trim().replace(/\/$/, '') || 'http://localhost:8100' })
  document.getElementById('saved').textContent = 'Saved'
})
