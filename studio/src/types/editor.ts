export type SheetType = 'apiDef' | 'singleCase' | 'bizFlow'

export interface ActiveSheet {
  index: number       // -1 = apiDef, 0 = singleCase, 1+ = bizFlow index
  type: SheetType
  name: string
}

export type Language = 'zh-CN' | 'en-US'
