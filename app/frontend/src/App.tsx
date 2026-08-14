import { useState, useRef, useCallback, useEffect, type DragEvent, type ChangeEvent } from 'react'
import {
  analyzeImage,
  fetchHealth,
  type AnalysisResult,
  type HealthResult,
  type Ingredient,
  type Recipe,
} from './api'

// ─── Types ────────────────────────────────────────────────────────────────────

interface GroceryItem {
  name: string
  recipeSource: string
  checked: boolean
}

type AppState = 'idle' | 'uploading' | 'analyzing' | 'results'

// ─── Category colors ──────────────────────────────────────────────────────────

const categoryStyles: Record<Ingredient['category'], { bg: string; text: string; dot: string }> = {
  protein:    { bg: 'bg-amber-50',   text: 'text-amber-800',  dot: 'bg-amber-400' },
  vegetable:  { bg: 'bg-green-50',   text: 'text-green-800',  dot: 'bg-green-500' },
  dairy:      { bg: 'bg-blue-50',    text: 'text-blue-800',   dot: 'bg-blue-400' },
  grain:      { bg: 'bg-yellow-50',  text: 'text-yellow-800', dot: 'bg-yellow-500' },
  condiment:  { bg: 'bg-orange-50',  text: 'text-orange-800', dot: 'bg-orange-400' },
  fruit:      { bg: 'bg-rose-50',    text: 'text-rose-800',   dot: 'bg-rose-400' },
  other:      { bg: 'bg-stone-100',  text: 'text-stone-700',  dot: 'bg-stone-400' },
}

const difficultyColor: Record<Recipe['difficulty'], string> = {
  Easy:        'text-green-700 bg-green-50',
  Medium:      'text-amber-700 bg-amber-50',
  Challenging: 'text-rose-700 bg-rose-50',
}

// ─── Grocery List Panel ───────────────────────────────────────────────────────

function GroceryPanel({
  items,
  onToggle,
  onRemove,
  onClear,
  onClose,
}: {
  items: GroceryItem[]
  onToggle: (name: string) => void
  onRemove: (name: string) => void
  onClear: () => void
  onClose: () => void
}) {
  // Group by recipe source
  const grouped = items.reduce<Record<string, GroceryItem[]>>((acc, item) => {
    if (!acc[item.recipeSource]) acc[item.recipeSource] = []
    acc[item.recipeSource].push(item)
    return acc
  }, {})

  const checkedCount = items.filter((i) => i.checked).length
  const totalCount = items.length

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(28,25,23,0.35)',
          backdropFilter: 'blur(2px)',
          zIndex: 100,
          animation: 'fadeIn 0.2s ease',
        }}
      />

      {/* Panel */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: 'min(420px, 100vw)',
          backgroundColor: 'var(--card)',
          borderLeft: '1px solid var(--border)',
          zIndex: 101,
          display: 'flex',
          flexDirection: 'column',
          animation: 'slideInRight 0.28s cubic-bezier(0.32,0,0.16,1)',
        }}
      >
        <style>{`
          @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
          @keyframes slideInRight { from { transform: translateX(100%); } to { transform: translateX(0); } }
        `}</style>

        {/* Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
          }}
        >
          <div>
            <h2
              style={{
                fontFamily: 'var(--font-serif)',
                fontSize: '1.25rem',
                fontWeight: 400,
                color: 'var(--foreground)',
                marginBottom: 2,
              }}
            >
              Grocery list
            </h2>
            {totalCount > 0 && (
              <p style={{ fontSize: '0.8125rem', color: 'var(--muted-foreground)' }}>
                {checkedCount} of {totalCount} collected
              </p>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {items.length > 0 && (
              <button
                onClick={onClear}
                style={{
                  fontSize: '0.75rem',
                  fontWeight: 500,
                  color: 'var(--muted-foreground)',
                  background: 'none',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  padding: '5px 10px',
                  cursor: 'pointer',
                }}
              >
                Clear all
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                width: 32,
                height: 32,
                borderRadius: 6,
                border: '1px solid var(--border)',
                background: 'none',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--muted-foreground)',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Progress bar */}
        {totalCount > 0 && (
          <div style={{ height: 3, backgroundColor: 'var(--muted)', flexShrink: 0 }}>
            <div
              style={{
                height: '100%',
                backgroundColor: 'var(--primary)',
                width: `${(checkedCount / totalCount) * 100}%`,
                transition: 'width 0.4s ease',
                borderRadius: '0 2px 2px 0',
              }}
            />
          </div>
        )}

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {items.length === 0 ? (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                gap: 12,
                padding: 32,
                textAlign: 'center',
              }}
            >
              <div
                style={{
                  width: 56,
                  height: 56,
                  borderRadius: '50%',
                  backgroundColor: 'var(--muted)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--muted-foreground)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
                  <line x1="3" y1="6" x2="21" y2="6" />
                  <path d="M16 10a4 4 0 0 1-8 0" />
                </svg>
              </div>
              <div>
                <p style={{ fontFamily: 'var(--font-serif)', fontSize: '1rem', color: 'var(--foreground)', marginBottom: 6 }}>
                  Your list is empty
                </p>
                <p style={{ fontSize: '0.8125rem', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
                  Add missing ingredients from any recipe card to build your shopping list.
                </p>
              </div>
            </div>
          ) : (
            <div>
              {Object.entries(grouped).map(([source, groupItems]) => (
                <div key={source} style={{ paddingBottom: 4 }}>
                  {/* Group header */}
                  <div
                    style={{
                      padding: '12px 24px 6px',
                      fontSize: '0.6875rem',
                      fontWeight: 600,
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                      color: 'var(--muted-foreground)',
                    }}
                  >
                    {source}
                  </div>
                  {groupItems.map((item) => (
                    <div
                      key={item.name}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 12,
                        padding: '9px 24px',
                        transition: 'background 0.15s',
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.backgroundColor = 'var(--muted)' }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent' }}
                    >
                      {/* Checkbox */}
                      <button
                        onClick={() => onToggle(item.name)}
                        style={{
                          width: 20,
                          height: 20,
                          borderRadius: 5,
                          border: item.checked ? 'none' : '1.5px solid var(--border)',
                          backgroundColor: item.checked ? 'var(--primary)' : 'transparent',
                          flexShrink: 0,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          transition: 'all 0.15s',
                        }}
                      >
                        {item.checked && (
                          <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="var(--primary-foreground)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="2,6 5,9 10,3" />
                          </svg>
                        )}
                      </button>

                      {/* Label */}
                      <span
                        style={{
                          flex: 1,
                          fontSize: '0.875rem',
                          color: item.checked ? 'var(--muted-foreground)' : 'var(--foreground)',
                          textDecoration: item.checked ? 'line-through' : 'none',
                          transition: 'all 0.2s',
                        }}
                      >
                        {item.name}
                      </span>

                      {/* Remove */}
                      <button
                        onClick={() => onRemove(item.name)}
                        style={{
                          width: 24,
                          height: 24,
                          borderRadius: 4,
                          border: 'none',
                          background: 'none',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: 'var(--muted-foreground)',
                          opacity: 0.5,
                          flexShrink: 0,
                        }}
                        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1' }}
                        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '0.5' }}
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M18 6L6 18M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer — copy to clipboard */}
        {items.length > 0 && (
          <div style={{ padding: '16px 24px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
            <CopyButton items={items} />
          </div>
        )}
      </div>
    </>
  )
}

function CopyButton({ items }: { items: GroceryItem[] }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = () => {
    const text = items
      .filter((i) => !i.checked)
      .map((i) => `• ${i.name}`)
      .join('\n')
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <button
      onClick={handleCopy}
      style={{
        width: '100%',
        padding: '10px',
        borderRadius: 8,
        border: '1px solid var(--border)',
        backgroundColor: copied ? 'var(--primary)' : 'transparent',
        color: copied ? 'var(--primary-foreground)' : 'var(--foreground)',
        fontSize: '0.875rem',
        fontWeight: 500,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 7,
        transition: 'all 0.2s',
      }}
    >
      {copied ? (
        <>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
          Copied!
        </>
      ) : (
        <>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
          </svg>
          Copy remaining items
        </>
      )}
    </button>
  )
}

// ─── Components ───────────────────────────────────────────────────────────────

function UploadZone({
  onFileSelected,
  isDragging,
  onDragEnter,
  onDragLeave,
  onDrop,
}: {
  onFileSelected: (file: File) => void
  isDragging: boolean
  onDragEnter: (e: DragEvent) => void
  onDragLeave: (e: DragEvent) => void
  onDrop: (e: DragEvent) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  return (
    <div
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={(e) => e.preventDefault()}
      onDrop={onDrop}
      onClick={() => inputRef.current?.click()}
      className="relative cursor-pointer rounded-xl border-2 border-dashed transition-all duration-300 group"
      style={{
        borderColor: isDragging ? 'var(--primary)' : 'var(--border)',
        backgroundColor: isDragging ? 'rgba(42,74,30,0.04)' : 'var(--card)',
        minHeight: '320px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '20px',
        padding: '48px 32px',
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e: ChangeEvent<HTMLInputElement>) => {
          const file = e.target.files?.[0]
          if (file) onFileSelected(file)
        }}
      />
      <div
        className="transition-transform duration-300 group-hover:scale-110"
        style={{
          width: 72,
          height: 72,
          borderRadius: '50%',
          backgroundColor: isDragging ? 'var(--primary)' : 'var(--muted)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'all 0.3s',
        }}
      >
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke={isDragging ? '#F7F3EE' : 'var(--muted-foreground)'} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
          <path d="M12 12v9" />
          <path d="m16 16-4-4-4 4" />
        </svg>
      </div>
      <div className="text-center" style={{ maxWidth: 320 }}>
        <p style={{ fontFamily: 'var(--font-serif)', fontSize: '1.25rem', fontWeight: 400, color: 'var(--foreground)', marginBottom: 8 }}>
          {isDragging ? 'Drop your photo here' : 'Upload a fridge or pantry photo'}
        </p>
        <p style={{ fontSize: '0.875rem', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>
          Drag & drop or click to browse. We'll identify your ingredients and suggest what to cook.
        </p>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.75rem', color: 'var(--muted-foreground)' }}>
        <span>JPG, PNG, HEIC</span>
        <span style={{ color: 'var(--border)' }}>·</span>
        <span>Up to 20 MB</span>
      </div>
    </div>
  )
}

function AnalyzingState({ imageUrl }: { imageUrl: string }) {
  const steps = ['Identifying ingredients…', 'Mapping what you have…', 'Finding the best recipes…']
  const [step, setStep] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => setStep((s) => Math.min(s + 1, steps.length - 1)), 900)
    return () => clearInterval(interval)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <div style={{ position: 'relative', borderRadius: 12, overflow: 'hidden', aspectRatio: '16/9', maxHeight: 320 }}>
        <img src={imageUrl} alt="Uploaded fridge" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(28,25,23,0.55)', backdropFilter: 'blur(2px)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
          <div style={{ position: 'relative', width: 48, height: 48 }}>
            <svg viewBox="0 0 48 48" style={{ width: 48, height: 48, animation: 'spin 1.2s linear infinite' }}>
              <circle cx="24" cy="24" r="20" fill="none" stroke="rgba(247,243,238,0.2)" strokeWidth="3" />
              <circle cx="24" cy="24" r="20" fill="none" stroke="#F7F3EE" strokeWidth="3" strokeDasharray="125.6" strokeDashoffset="94.2" strokeLinecap="round" />
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
            </svg>
          </div>
          <p style={{ fontFamily: 'var(--font-serif)', color: '#F7F3EE', fontSize: '1.1rem', fontWeight: 300 }}>
            {steps[step]}
          </p>
        </div>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 32, width: 60 + (i % 4) * 20, borderRadius: 20 }} />
        ))}
      </div>
    </div>
  )
}

function IngredientTag({ ingredient, index }: { ingredient: Ingredient; index: number }) {
  const style = categoryStyles[ingredient.category]
  return (
    <div
      className={`animate-fade-slide-up ${style.bg} ${style.text}`}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 20, fontSize: '0.8125rem', fontWeight: 500, animationDelay: `${index * 60}ms`, opacity: 0 }}
    >
      <span className={style.dot} style={{ width: 6, height: 6, borderRadius: '50%', flexShrink: 0 }} />
      {ingredient.name}
      {ingredient.confidence === 'medium' && <span style={{ opacity: 0.5, fontSize: '0.7rem' }}>~</span>}
    </div>
  )
}

/** Deterministic stand-in for recipes whose photo isn't in the local photo set. */
function RecipePlaceholder({ name }: { name: string }) {
  // Hash the name so a given dish always renders the same plate.
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0
  const hue = Math.abs(hash) % 360
  const initials = name
    .split(/\s+/)
    .filter((w) => /[a-z]/i.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')

  return (
    <div
      aria-hidden
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: `linear-gradient(135deg, hsl(${hue} 32% 88%), hsl(${(hue + 40) % 360} 28% 78%))`,
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '2.25rem',
          fontWeight: 300,
          color: `hsl(${hue} 40% 32%)`,
          letterSpacing: '0.04em',
        }}
      >
        {initials || '·'}
      </span>
    </div>
  )
}

function RecipeCard({
  recipe,
  index,
  onAddToGrocery,
  addedToGrocery,
}: {
  recipe: Recipe
  index: number
  onAddToGrocery: (recipe: Recipe) => void
  addedToGrocery: boolean
}) {
  const [hovered, setHovered] = useState(false)

  return (
    <div
      className="animate-fade-slide-up"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        animationDelay: `${index * 80}ms`,
        opacity: 0,
        backgroundColor: 'var(--card)',
        borderRadius: 12,
        overflow: 'hidden',
        border: '1px solid var(--border)',
        transition: 'transform 0.25s ease, box-shadow 0.25s ease',
        transform: hovered ? 'translateY(-3px)' : 'none',
        boxShadow: hovered ? '0 12px 32px rgba(28,25,23,0.10)' : '0 1px 3px rgba(28,25,23,0.06)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Image — the corpus ships photo paths but the photo set is optional, so
          a recipe with no local image gets a generated monogram plate instead. */}
      <div style={{ position: 'relative', height: 180, backgroundColor: 'var(--muted)', overflow: 'hidden', flexShrink: 0 }}>
        {recipe.image ? (
          <img src={recipe.image} alt={recipe.name} style={{ width: '100%', height: '100%', objectFit: 'cover', transition: 'transform 0.4s ease', transform: hovered ? 'scale(1.04)' : 'scale(1)' }} />
        ) : (
          <RecipePlaceholder name={recipe.name} />
        )}
        <div style={{ position: 'absolute', top: 12, right: 12, backgroundColor: 'var(--primary)', color: 'var(--primary-foreground)', padding: '3px 10px', borderRadius: 20, fontSize: '0.75rem', fontWeight: 500 }}>
          {recipe.matchedIngredients.length} matches
        </div>
        <div
          title={`Jaccard similarity ${recipe.score.toFixed(3)} · uses ${(recipe.coverage * 100).toFixed(0)}% of what you have`}
          style={{ position: 'absolute', bottom: 12, left: 12, backgroundColor: 'rgba(28,25,23,0.72)', color: '#F7F3EE', padding: '3px 9px', borderRadius: 20, fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.03em', backdropFilter: 'blur(3px)' }}
        >
          {recipe.score.toFixed(2)} match
        </div>
      </div>

      {/* Body */}
      <div style={{ padding: '20px 20px 0', flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          <span className={difficultyColor[recipe.difficulty]} style={{ fontSize: '0.7rem', fontWeight: 600, padding: '2px 8px', borderRadius: 10, letterSpacing: '0.04em', textTransform: 'uppercase' }}>
            {recipe.difficulty}
          </span>
          {recipe.tags.slice(0, 2).map((t) => (
            <span key={t} style={{ fontSize: '0.7rem', fontWeight: 500, padding: '2px 8px', borderRadius: 10, color: 'var(--muted-foreground)', backgroundColor: 'var(--muted)' }}>
              {t}
            </span>
          ))}
        </div>

        <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.0625rem', fontWeight: 400, color: 'var(--foreground)', marginBottom: 8, lineHeight: 1.35 }}>
          {recipe.name}
        </h3>

        <p style={{ fontSize: '0.8125rem', color: 'var(--muted-foreground)', lineHeight: 1.6, marginBottom: 14, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {recipe.description}
        </p>

        {/* You have */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 12 }}>
          {recipe.matchedIngredients.slice(0, 3).map((ing) => (
            <span key={ing} style={{ fontSize: '0.7rem', padding: '2px 7px', borderRadius: 4, border: '1px solid var(--border)', color: 'var(--muted-foreground)' }}>
              {ing}
            </span>
          ))}
          {recipe.matchedIngredients.length > 3 && (
            <span style={{ fontSize: '0.7rem', padding: '2px 7px', color: 'var(--accent)', fontWeight: 500 }}>
              +{recipe.matchedIngredients.length - 3} more
            </span>
          )}
        </div>

        {/* Missing ingredients */}
        {recipe.missingIngredients.length > 0 && (
          <div
            style={{
              backgroundColor: 'var(--muted)',
              borderRadius: 8,
              padding: '10px 12px',
              marginBottom: 14,
            }}
          >
            <p style={{ fontSize: '0.7rem', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted-foreground)', marginBottom: 6 }}>
              Need to buy
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {/* Real recipes can want 15+ things you don't have; the card shows
                  the first six and the button still adds the whole list. */}
              {recipe.missingIngredients.slice(0, 6).map((ing) => (
                <span
                  key={ing}
                  style={{
                    fontSize: '0.75rem',
                    padding: '2px 8px',
                    borderRadius: 4,
                    backgroundColor: 'rgba(196,98,45,0.1)',
                    color: 'var(--accent)',
                    fontWeight: 500,
                  }}
                >
                  {ing}
                </span>
              ))}
              {recipe.missingIngredients.length > 6 && (
                <span style={{ fontSize: '0.75rem', padding: '2px 4px', color: 'var(--muted-foreground)', fontWeight: 500 }}>
                  +{recipe.missingIngredients.length - 6} more
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={{ padding: '0 20px 16px' }}>
        <div style={{ paddingTop: 14, borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
          <div
            title={recipe.timeEstimated
              ? 'Estimated from step and ingredient count — this recipe never states a time'
              : 'Summed from the times stated in the recipe steps'}
            style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--muted-foreground)', fontSize: '0.8125rem' }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            {recipe.timeEstimated ? '~' : ''}{recipe.time}
          </div>

          {recipe.missingIngredients.length > 0 && (
            <button
              onClick={(e) => { e.stopPropagation(); onAddToGrocery(recipe) }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 5,
                fontSize: '0.8125rem',
                fontWeight: 500,
                color: addedToGrocery ? 'var(--primary)' : 'var(--accent)',
                background: addedToGrocery ? 'rgba(42,74,30,0.08)' : 'rgba(196,98,45,0.08)',
                border: 'none',
                borderRadius: 6,
                padding: '5px 10px',
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              {addedToGrocery ? (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Added
                </>
              ) : (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
                    <line x1="3" y1="6" x2="21" y2="6" />
                    <path d="M16 10a4 4 0 0 1-8 0" />
                  </svg>
                  Add to list
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Status surfaces ──────────────────────────────────────────────────────────

function Banner({ tone, title, body }: { tone: 'warning' | 'error'; title: string; body: string }) {
  const palette = tone === 'error'
    ? { bg: 'rgba(196,98,45,0.08)', border: 'rgba(196,98,45,0.28)', fg: 'var(--accent)' }
    : { bg: 'rgba(120,113,108,0.08)', border: 'var(--border)', fg: 'var(--muted-foreground)' }

  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      style={{
        marginBottom: 20,
        padding: '14px 16px',
        borderRadius: 10,
        backgroundColor: palette.bg,
        border: `1px solid ${palette.border}`,
        display: 'flex',
        gap: 12,
        alignItems: 'flex-start',
      }}
    >
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke={palette.fg} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: 1 }}>
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <div>
        <p style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--foreground)', marginBottom: 3 }}>{title}</p>
        <p style={{ fontSize: '0.8125rem', color: 'var(--muted-foreground)', lineHeight: 1.6 }}>{body}</p>
      </div>
    </div>
  )
}

/** Turns /api/health into something a human can act on. */
function backendHint(health: HealthResult): { title: string; body: string } {
  const missing: string[] = []
  if (!health.detector.ready) missing.push('the detector weights')
  if (!health.recipes.ready) missing.push('the recipe corpus')

  return {
    title: 'The models are not loaded yet',
    body:
      `The backend is running but ${missing.join(' and ')} could not be loaded, so uploads will fail. ` +
      (health.detector.error || health.recipes.error || '') +
      ' See app/README.md for which files to place in app/backend/artifacts/.',
  }
}

/** Provenance strip — what actually produced the results on screen. */
function RunSummary({ meta }: { meta: AnalysisResult['meta'] }) {
  const facts = [
    `${meta.detections} boxes → ${meta.ingredientsFound} ingredients`,
    `YOLOv8s @ conf ${meta.detector.confThreshold}`,
    `Jaccard over ${meta.retriever.corpusSize.toLocaleString()} recipes`,
    `${meta.timingMs.detect.toFixed(0)} ms detect · ${meta.timingMs.rank.toFixed(0)} ms rank`,
  ]

  return (
    <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)', display: 'flex', flexWrap: 'wrap', gap: '6px 14px' }}>
      {facts.map((fact) => (
        <span key={fact} style={{ fontSize: '0.6875rem', color: 'var(--muted-foreground)', letterSpacing: '0.02em' }}>
          {fact}
        </span>
      ))}
      {meta.ingredientsNotInCorpus.length > 0 && (
        <span
          title={meta.ingredientsNotInCorpus.join(', ')}
          style={{ fontSize: '0.6875rem', color: 'var(--muted-foreground)', letterSpacing: '0.02em' }}
        >
          {meta.ingredientsNotInCorpus.length} not in corpus
        </span>
      )}
    </div>
  )
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [state, setState] = useState<AppState>('idle')
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [filter, setFilter] = useState<string>('all')
  const [groceryItems, setGroceryItems] = useState<GroceryItem[]>([])
  const [groceryOpen, setGroceryOpen] = useState(false)
  const [addedRecipes, setAddedRecipes] = useState<Set<string>>(new Set())
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthResult | null>(null)

  const objectUrlRef = useRef<string | null>(null)

  const ingredients: Ingredient[] = result?.ingredients ?? []
  const recipes: Recipe[] = result?.recipes ?? []

  // Only offer filters for categories actually present in this result.
  const categories = [
    'all',
    ...['vegetable', 'protein', 'dairy', 'fruit', 'grain', 'condiment', 'other'].filter((c) =>
      ingredients.some((i) => i.category === c)
    ),
  ]

  // Surface a cold backend before the user wastes an upload on it.
  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal).then(setHealth).catch(() => setHealth(null))
    return () => controller.abort()
  }, [])

  // Revoke the previous preview URL on replace/unmount so repeated uploads
  // don't leak blobs.
  useEffect(() => {
    return () => {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    }
  }, [])

  const handleFile = useCallback(async (file: File) => {
    if (!file.type.startsWith('image/')) {
      setError('That file is not an image. Upload a JPG, PNG or HEIC photo.')
      return
    }

    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current)
    const url = URL.createObjectURL(file)
    objectUrlRef.current = url

    setImageUrl(url)
    setError(null)
    setResult(null)
    setFilter('all')
    setState('analyzing')

    try {
      const analysis = await analyzeImage(file)
      setResult(analysis)
      if (analysis.ingredients.length === 0) {
        setError(
          'No ingredients were detected in that photo. Try a brighter shot with the fridge door open and items facing the camera.'
        )
        setState('idle')
        return
      }
      setState('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed.')
      setState('idle')
    }
  }, [])

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault()
      setIsDragging(false)
      const file = e.dataTransfer.files[0]
      if (file) void handleFile(file)
    },
    [handleFile]
  )

  const handleAddToGrocery = useCallback((recipe: Recipe) => {
    // Keyed by id, not name — the corpus contains genuine duplicate dish names.
    setAddedRecipes((prev) => new Set([...prev, recipe.id]))
    setGroceryItems((prev) => {
      const existing = new Set(prev.map((i) => i.name))
      const newItems = recipe.missingIngredients
        .filter((ing) => !existing.has(ing))
        .map((ing) => ({ name: ing, recipeSource: recipe.name, checked: false }))
      return [...prev, ...newItems]
    })
    setGroceryOpen(true)
  }, [])

  const handleToggle = useCallback((name: string) => {
    setGroceryItems((prev) =>
      prev.map((i) => (i.name === name ? { ...i, checked: !i.checked } : i))
    )
  }, [])

  const handleRemove = useCallback((name: string) => {
    setGroceryItems((prev) => prev.filter((i) => i.name !== name))
  }, [])

  const handleClear = useCallback(() => {
    setGroceryItems([])
    setAddedRecipes(new Set())
  }, [])

  const handleReset = useCallback(() => {
    setState('idle')
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    setImageUrl(null)
    setResult(null)
    setError(null)
    setFilter('all')
    setGroceryItems([])
    setAddedRecipes(new Set())
  }, [])

  const filteredIngredients =
    filter === 'all' ? ingredients : ingredients.filter((i) => i.category === filter)

  const uncheckedCount = groceryItems.filter((i) => !i.checked).length

  return (
    <div style={{ minHeight: '100vh', backgroundColor: 'var(--background)' }}>
      {/* Header */}
      <header style={{ borderBottom: '1px solid var(--border)', backgroundColor: 'var(--card)', padding: '0 24px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, zIndex: 50 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span style={{ fontFamily: 'var(--font-serif)', fontSize: '1.3125rem', fontWeight: 400, color: 'var(--foreground)', letterSpacing: '-0.01em' }}>
            Larder
          </span>
          <span style={{ fontSize: '0.6875rem', fontWeight: 600, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--accent)' }}>
            AI
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {/* Grocery list button */}
          {state === 'results' && (
            <button
              onClick={() => setGroceryOpen(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 7,
                fontSize: '0.875rem',
                fontWeight: 500,
                color: groceryItems.length > 0 ? 'var(--primary)' : 'var(--muted-foreground)',
                backgroundColor: groceryItems.length > 0 ? 'rgba(42,74,30,0.08)' : 'transparent',
                border: '1px solid',
                borderColor: groceryItems.length > 0 ? 'rgba(42,74,30,0.2)' : 'var(--border)',
                borderRadius: 8,
                padding: '6px 14px',
                cursor: 'pointer',
                transition: 'all 0.2s',
                position: 'relative',
              }}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <path d="M16 10a4 4 0 0 1-8 0" />
              </svg>
              Grocery list
              {uncheckedCount > 0 && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    minWidth: 18,
                    height: 18,
                    borderRadius: 9,
                    backgroundColor: 'var(--accent)',
                    color: '#fff',
                    fontSize: '0.6875rem',
                    fontWeight: 700,
                    padding: '0 5px',
                  }}
                >
                  {uncheckedCount}
                </span>
              )}
            </button>
          )}

          {state === 'results' && (
            <button
              onClick={handleReset}
              style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8125rem', fontWeight: 500, color: 'var(--muted-foreground)', background: 'none', border: '1px solid var(--border)', borderRadius: 6, padding: '6px 12px', cursor: 'pointer' }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              New photo
            </button>
          )}
        </div>
      </header>

      {/* Main */}
      <main style={{ maxWidth: 1160, margin: '0 auto', padding: '40px 24px 80px' }}>
        {/* Hero */}
        {state === 'idle' && (
          <div style={{ textAlign: 'center', marginBottom: 48 }}>
            <p style={{ fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: 16 }}>
              From fridge to fork
            </p>
            <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 'clamp(2rem, 5vw, 3.25rem)', fontWeight: 300, color: 'var(--foreground)', lineHeight: 1.15, letterSpacing: '-0.02em', marginBottom: 20 }}>
              What's in your kitchen<span style={{ fontStyle: 'italic' }}>?</span>
            </h1>
            <p style={{ fontSize: '1rem', color: 'var(--muted-foreground)', maxWidth: 460, margin: '0 auto', lineHeight: 1.7 }}>
              Upload a photo of your fridge or pantry. We'll identify your ingredients and find the best recipes you can make right now.
            </p>
          </div>
        )}

        {state === 'idle' && (
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            {health && !health.ready && <Banner tone="warning" {...backendHint(health)} />}
            {error && <Banner tone="error" title="Couldn't analyse that photo" body={error} />}

            <UploadZone
              onFileSelected={(f) => void handleFile(f)}
              isDragging={isDragging}
              onDragEnter={(e) => { e.preventDefault(); setIsDragging(true) }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
            />
            <p style={{ textAlign: 'center', marginTop: 20, fontSize: '0.8125rem', color: 'var(--muted-foreground)' }}>
              Works best with open fridge doors and well-lit pantry shelves.
            </p>
          </div>
        )}

        {(state === 'uploading' || state === 'analyzing') && imageUrl && (
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            <AnalyzingState imageUrl={imageUrl} />
          </div>
        )}

        {/* Results */}
        {state === 'results' && (
          <div>
            {/* Image + ingredients */}
            <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 32, marginBottom: 48, alignItems: 'start' }}>
              <div style={{ borderRadius: 12, overflow: 'hidden', aspectRatio: '4/3', backgroundColor: 'var(--muted)', flexShrink: 0 }}>
                {imageUrl && <img src={imageUrl} alt="Your fridge" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />}
              </div>

              <div>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 20, gap: 12, flexWrap: 'wrap' }}>
                  <div>
                    <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.5rem', fontWeight: 400, color: 'var(--foreground)', marginBottom: 4 }}>
                      {ingredients.length} ingredient{ingredients.length === 1 ? '' : 's'} found
                    </h2>
                    <p style={{ fontSize: '0.8125rem', color: 'var(--muted-foreground)' }}>
                      {recipes.length > 0
                        ? `Enough for ${recipes.length} recipe${recipes.length === 1 ? '' : 's'}`
                        : 'No recipe in the corpus uses enough of these together'}
                    </p>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 16 }}>
                  {categories.map((cat) => (
                    <button
                      key={cat}
                      onClick={() => setFilter(cat)}
                      style={{ fontSize: '0.75rem', fontWeight: 500, padding: '4px 12px', borderRadius: 20, border: '1px solid', borderColor: filter === cat ? 'var(--primary)' : 'var(--border)', backgroundColor: filter === cat ? 'var(--primary)' : 'transparent', color: filter === cat ? 'var(--primary-foreground)' : 'var(--muted-foreground)', cursor: 'pointer', transition: 'all 0.15s', textTransform: 'capitalize' }}
                    >
                      {cat === 'all' ? `All (${ingredients.length})` : cat}
                    </button>
                  ))}
                </div>

                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {filteredIngredients.map((ing, i) => (
                    <IngredientTag key={ing.key} ingredient={ing} index={i} />
                  ))}
                </div>

                {result && <RunSummary meta={result.meta} />}
              </div>
            </div>

            {/* Recipes */}
            <div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 28, paddingBottom: 20, borderBottom: '1px solid var(--border)' }}>
                <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.75rem', fontWeight: 400, color: 'var(--foreground)', letterSpacing: '-0.01em' }}>
                  Suggested recipes
                </h2>
                <span style={{ fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted-foreground)' }}>
                  {recipes.length} matches
                </span>
              </div>

              {recipes.length === 0 ? (
                <p style={{ fontSize: '0.9375rem', color: 'var(--muted-foreground)', lineHeight: 1.7, maxWidth: 520 }}>
                  Your ingredients were identified, but no recipe in the {result?.meta.retriever.corpusSize.toLocaleString()}-recipe
                  corpus uses at least {result?.meta.retriever.minMatches} of them together. Try a photo showing more of
                  your staples.
                </p>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 24 }}>
                  {recipes.map((recipe, i) => (
                    <RecipeCard
                      key={recipe.id}
                      recipe={recipe}
                      index={i}
                      onAddToGrocery={handleAddToGrocery}
                      addedToGrocery={addedRecipes.has(recipe.id)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* Grocery panel */}
      {groceryOpen && (
        <GroceryPanel
          items={groceryItems}
          onToggle={handleToggle}
          onRemove={handleRemove}
          onClear={handleClear}
          onClose={() => setGroceryOpen(false)}
        />
      )}
    </div>
  )
}
