// Client for the FridgeFest backend. Shapes mirror fridgefest/pipeline.py exactly.

export type IngredientCategory =
  | 'protein'
  | 'vegetable'
  | 'dairy'
  | 'grain'
  | 'condiment'
  | 'fruit'
  | 'other'

export interface Ingredient {
  key: string
  name: string
  detectedAs: string
  category: IngredientCategory
  confidence: 'high' | 'medium'
  score: number
  count: number
  boxes: number[][]
}

export interface Recipe {
  id: string
  name: string
  time: string
  timeEstimated: boolean
  difficulty: 'Easy' | 'Medium' | 'Challenging'
  description: string
  matchedIngredients: string[]
  missingIngredients: string[]
  image: string | null
  tags: string[]
  score: number
  coverage: number
  totalIngredients: number
}

export interface AnalysisMeta {
  detections: number
  ingredientsFound: number
  recipesReturned: number
  ingredientsNotInCorpus: string[]
  detector: {
    weights: string
    confThreshold: number
    iouThreshold: number
    imageSize: number
  }
  retriever: {
    method: string
    space: string
    corpusSize: number
    minMatches: number
  }
  timingMs: { detect: number; rank: number }
  imageSize?: { width: number; height: number }
}

export interface AnalysisResult {
  ingredients: Ingredient[]
  recipes: Recipe[]
  meta: AnalysisMeta
}

export interface RecipeDetail {
  id: string
  name: string
  time: string
  timeEstimated: boolean
  difficulty: 'Easy' | 'Medium' | 'Challenging'
  description: string
  ingredients: string[]
  instructions: string[]
  image: string | null
  tags: string[]
  totalIngredients: number
}

export interface HealthResult {
  ready: boolean
  detector: { ready: boolean; weights: string | null; classes: number; error: string | null }
  recipes: {
    ready: boolean
    source: string | null
    count: number
    detectableClasses: number
    photos: boolean
    error: string | null
  }
  notes: string[]
}

/** Pull a useful message out of FastAPI's `detail`, which may be object or string. */
async function errorMessage(response: Response): Promise<string> {
  let detail: unknown
  try {
    detail = (await response.json())?.detail
  } catch {
    return `${response.status} ${response.statusText}`
  }

  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const d = detail as Record<string, unknown>
    const parts = [d.message, d.detector, d.recipes].filter(
      (p): p is string => typeof p === 'string' && p.length > 0
    )
    if (parts.length) return parts.join(' — ')
  }
  return `${response.status} ${response.statusText}`
}

export async function analyzeImage(file: File, signal?: AbortSignal): Promise<AnalysisResult> {
  const body = new FormData()
  body.append('image', file)

  const response = await fetch('/api/analyze', { method: 'POST', body, signal })
  if (!response.ok) throw new Error(await errorMessage(response))
  return response.json()
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResult> {
  const response = await fetch('/api/health', { signal })
  if (!response.ok) throw new Error(await errorMessage(response))
  return response.json()
}

export async function fetchRecipeDetail(id: string, signal?: AbortSignal): Promise<RecipeDetail> {
  const response = await fetch(`/api/recipes/${encodeURIComponent(id)}`, { signal })
  if (!response.ok) throw new Error(await errorMessage(response))
  return response.json()
}
