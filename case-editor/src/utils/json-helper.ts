import type { JsonNode, JsonType } from '../types/excel'

/**
 * Parse a JSON string into a tree of JsonNodes for the editor.
 */
export function parseJsonToNodes(raw: string): JsonNode[] {
  let obj: unknown
  try {
    obj = JSON.parse(raw)
  } catch {
    return []
  }
  return objToNodes('', obj) as JsonNode[]
}

/**
 * Serialize a tree of JsonNodes back to a JSON string.
 */
export function nodesToJson(nodes: JsonNode[]): string {
  const result = nodesToObj(nodes)
  return JSON.stringify(result, null, 2)
}

// --- Internal helpers ---

function objToNodes(key: string, val: unknown): JsonNode[] | JsonNode {
  if (val === null || val === undefined) {
    return { key, type: 'string', value: '' }
  }

  if (Array.isArray(val)) {
    const children = val.map((item, i) => objToNodes(String(i), item) as JsonNode)
    return { key, type: 'List', value: children }
  }

  if (typeof val === 'object' && val !== null) {
    const children = Object.entries(val as Record<string, unknown>).map(
      ([k, v]) => objToNodes(k, v) as JsonNode
    )
    return { key, type: 'Dict', value: children }
  }

  return { key, type: inferPrimitiveType(val), value: val }
}

function nodesToObj(nodes: JsonNode[]): unknown {
  // If nodes represent a dict (all have non-numeric keys), return an object
  const result: Record<string, unknown> = {}
  for (const node of nodes) {
    result[node.key] = nodeToValue(node)
  }
  return result
}

function nodeToValue(node: JsonNode): unknown {
  switch (node.type) {
    case 'string':
      return String(node.value)
    case 'number':
      return Number(node.value)
    case 'boolean':
      return node.value === true || node.value === 'true'
    case 'Date':
      return String(node.value)
    case 'List':
      return (node.value as JsonNode[]).map((n) => nodeToValue(n))
    case 'Dict':
      // eslint-disable-next-line no-case-declarations
      const obj: Record<string, unknown> = {}
      for (const child of node.value as JsonNode[]) {
        obj[child.key] = nodeToValue(child)
      }
      return obj
    default:
      return String(node.value)
  }
}

function inferPrimitiveType(val: unknown): JsonType {
  if (typeof val === 'string') return 'string'
  if (typeof val === 'number') return 'number'
  if (typeof val === 'boolean') return 'boolean'
  return 'string'
}

/**
 * Create a default empty node of a given type.
 */
export function createDefaultNode(type: JsonType, key = ''): JsonNode {
  switch (type) {
    case 'string':
      return { key, type: 'string', value: '' }
    case 'number':
      return { key, type: 'number', value: 0 }
    case 'boolean':
      return { key, type: 'boolean', value: false }
    case 'Date':
      return { key, type: 'Date', value: '' }
    case 'List':
      return { key, type: 'List', value: [] }
    case 'Dict':
      return { key, type: 'Dict', value: [] }
    default:
      return { key, type: 'string', value: '' }
  }
}

/**
 * Guess the JSON type from a value.
 */
export function guessType(val: unknown): JsonType {
  if (val === null || val === undefined) return 'string'
  if (Array.isArray(val)) return 'List'
  if (typeof val === 'object') return 'Dict'
  if (typeof val === 'boolean') return 'boolean'
  if (typeof val === 'number') return 'number'
  return 'string'
}

/**
 * Convert a JsonNode tree to a plain JS value (object/array/primitive).
 */
export function jsonNodeToPlain(node: JsonNode): unknown {
  return nodeToValue(node)
}

/**
 * Convert a plain JS value to a JsonNode.
 */
export function plainToJsonNode(key: string, val: unknown): JsonNode {
  return objToNodes(key, val) as JsonNode
}
