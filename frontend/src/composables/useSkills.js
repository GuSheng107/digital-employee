import { ref } from 'vue'
import { ElMessage } from 'element-plus/es/components/message/index.mjs'
import { getSkills, setSkillEnabled, uploadSkills as uploadSkillsApi, deleteSkill as deleteSkillApi, parseSkills as parseSkillsApi } from '../api/skills'

export function useSkills() {
  const uploadingSkills = ref(false)
  const loadingSkills = ref(false)

  async function scanSkills() {
    loadingSkills.value = true
    try {
      await getSkills()
      ElMessage.success('技能已刷新')
    } catch (error) {
      ElMessage.error(String(error))
    } finally {
      loadingSkills.value = false
    }
  }

  async function uploadSkills(file, displayNames, type = 'new', skillName = '') {
    uploadingSkills.value = true
    try {
      await uploadSkillsApi(file, displayNames, type, skillName)
      ElMessage.success('技能已上传')
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    } finally {
      uploadingSkills.value = false
    }
  }

  async function deleteSkill(skillName) {
    try {
      await deleteSkillApi(skillName)
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    }
  }

  async function toggleSkill(skillName, enabled) {
    try {
      await setSkillEnabled(skillName, enabled)
      return true
    } catch (error) {
      ElMessage.error(String(error))
      return false
    }
  }

  async function parseSkills(file) {
    try {
      return await parseSkillsApi(file)
    } catch (error) {
      ElMessage.error(String(error))
      return null
    }
  }

  return {
    loadingSkills,
    uploadingSkills,
    scanSkills,
    uploadSkills,
    deleteSkill,
    toggleSkill,
    parseSkills,
  }
}
