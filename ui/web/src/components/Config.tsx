/** Configuration — the payer edits its own medical-necessity policy and clinical-criteria corpus
 * (both DB-backed; edits take effect on the next case). Reads are visible to any org for
 * transparency; write controls render only when the API says the caller may edit (the payer). */

import { useCallback, useEffect, useState } from 'react'
import { SlidersHorizontal, Plus, X, Pencil, Trash2, Check, Lock } from 'lucide-react'
import { configApi, type PolicyRule, type CriterionItem } from '../api'
import { Badge, Button, Input } from './ui'

const csv = (a: string[]) => a.join(', ')
const parse = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean)

export default function Config() {
  const [tab, setTab] = useState<'policy' | 'criteria'>('policy')
  return (
    <div>
      <div className="mb-6 flex items-start gap-3">
        <span className="mt-0.5 text-pine"><SlidersHorizontal size={22} strokeWidth={1.75} /></span>
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">Configuration</h1>
          <p className="mt-0.5 text-[13px] text-ink-soft">The payer's medical-necessity policy and clinical criteria — edited here, applied to the next case.</p>
        </div>
      </div>
      <div className="mb-6 inline-flex gap-1 rounded-md border border-line bg-paper p-1">
        {(['policy', 'criteria'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded-sm px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.12em] transition-colors ${
              tab === t ? 'bg-pine/10 text-pine' : 'text-ink-soft hover:text-ink'}`}>
            {t === 'policy' ? 'Policy rules' : 'Clinical criteria'}
          </button>
        ))}
      </div>
      {tab === 'policy' ? <PolicyTab /> : <CriteriaTab />}
    </div>
  )
}

function ReadOnlyNote() {
  return (
    <p className="mb-4 inline-flex items-center gap-1.5 rounded-sm border border-line bg-sunk/60 px-3 py-1.5 text-[12px] text-ink-soft">
      <Lock size={12} strokeWidth={1.75} /> Read-only — this is the payer's configuration.
    </p>
  )
}

// ---- Policy ---------------------------------------------------------------------

const EMPTY_RULE: PolicyRule = {
  procedure_code: '', required_diagnosis_prefixes: [], required_docs: [],
  step_therapy_docs: [], red_flag_prefixes: [], auto_approve: false,
}

function PolicyTab() {
  const [rules, setRules] = useState<PolicyRule[] | null>(null)
  const [editable, setEditable] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)  // code being edited, or '__new__'
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => configApi.policy().then((r) => { setRules(r.rules); setEditable(r.editable) }).catch((e) => setError(String(e?.message || e))), [])
  useEffect(() => { load() }, [load])

  if (rules === null) return <p className="text-[13px] text-ink-faint">Loading…</p>
  return (
    <div>
      {!editable && <ReadOnlyNote />}
      {error && <p className="mb-3 text-[13px] text-coral">{error}</p>}
      <div className="space-y-3">
        {rules.map((r) => (
          editing === r.procedure_code
            ? <PolicyForm key={r.procedure_code} initial={r} isNew={false} onDone={() => { setEditing(null); load() }} onCancel={() => setEditing(null)} />
            : <PolicyCard key={r.procedure_code} rule={r} editable={editable} onEdit={() => setEditing(r.procedure_code)} onDeleted={load} />
        ))}
        {editing === '__new__'
          ? <PolicyForm initial={EMPTY_RULE} isNew onDone={() => { setEditing(null); load() }} onCancel={() => setEditing(null)} />
          : editable && <Button variant="secondary" size="sm" leadingIcon={<Plus size={14} strokeWidth={1.75} />} onClick={() => setEditing('__new__')}>Add policy rule</Button>}
      </div>
    </div>
  )
}

function Chips({ label, items, tone }: { label: string; items: string[]; tone: 'pine' | 'ink' | 'coral' | 'neutral' }) {
  if (!items.length) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">{label}</span>
      {items.map((x) => <Badge key={x} tone={tone}>{x}</Badge>)}
    </div>
  )
}

function PolicyCard({ rule, editable, onEdit, onDeleted }: { rule: PolicyRule; editable: boolean; onEdit: () => void; onDeleted: () => void }) {
  const [busy, setBusy] = useState(false)
  const del = async () => { setBusy(true); try { await configApi.deletePolicy(rule.procedure_code); onDeleted() } finally { setBusy(false) } }
  return (
    <section className="rounded-md border border-line bg-paper p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[14px] font-semibold text-ink">{rule.procedure_code}</span>
          {rule.auto_approve && <Badge tone="pine">auto-approve</Badge>}
        </div>
        {editable && (
          <div className="flex items-center gap-1">
            <button onClick={onEdit} className="rounded-sm p-1.5 text-ink-faint hover:bg-sunk hover:text-pine" aria-label="Edit"><Pencil size={14} strokeWidth={1.75} /></button>
            <button onClick={del} disabled={busy} className="rounded-sm p-1.5 text-ink-faint hover:bg-sunk hover:text-coral" aria-label="Delete"><Trash2 size={14} strokeWidth={1.75} /></button>
          </div>
        )}
      </div>
      <div className="space-y-1.5">
        <Chips label="dx prefixes" items={rule.required_diagnosis_prefixes} tone="neutral" />
        <Chips label="required docs" items={rule.required_docs} tone="ink" />
        <Chips label="step therapy" items={rule.step_therapy_docs} tone="coral" />
        <Chips label="red flags" items={rule.red_flag_prefixes} tone="coral" />
      </div>
    </section>
  )
}

function PolicyForm({ initial, isNew, onDone, onCancel }: { initial: PolicyRule; isNew: boolean; onDone: () => void; onCancel: () => void }) {
  const [code, setCode] = useState(initial.procedure_code)
  const [dx, setDx] = useState(csv(initial.required_diagnosis_prefixes))
  const [docs, setDocs] = useState(csv(initial.required_docs))
  const [step, setStep] = useState(csv(initial.step_therapy_docs))
  const [red, setRed] = useState(csv(initial.red_flag_prefixes))
  const [auto, setAuto] = useState(initial.auto_approve)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    setBusy(true); setError(null)
    try {
      await configApi.savePolicy({
        procedure_code: code.trim().toUpperCase(), required_diagnosis_prefixes: parse(dx),
        required_docs: parse(docs), step_therapy_docs: parse(step), red_flag_prefixes: parse(red), auto_approve: auto,
      })
      onDone()
    } catch (e) { setError(String((e as Error)?.message || e)) } finally { setBusy(false) }
  }
  const Row = ({ label, value, set, ph }: { label: string; value: string; set: (v: string) => void; ph: string }) => (
    <label className="block">
      <span className="mb-1 block font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">{label}</span>
      <Input value={value} onChange={(e) => set(e.target.value)} placeholder={ph} />
    </label>
  )
  return (
    <section className="rounded-md border border-pine/30 bg-pine/[0.03] p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">Procedure code</span>
          <Input value={code} disabled={!isNew} onChange={(e) => setCode(e.target.value.toUpperCase())} placeholder="72148" />
        </label>
        <label className="flex items-end gap-2 pb-2 text-[13px] text-ink">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="h-4 w-4 accent-pine" /> Auto-approve
        </label>
      </div>
      <p className="mt-2 mb-3 text-[11px] text-ink-faint">Comma-separated. Prefixes match ICD-10 (e.g. M54, G83.4); docs are tokens (e.g. conservative_therapy_notes).</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Row label="Required dx prefixes" value={dx} set={setDx} ph="M54, M51" />
        <Row label="Required docs" value={docs} set={setDocs} ph="conservative_therapy_notes" />
        <Row label="Step-therapy docs" value={step} set={setStep} ph="step_therapy_record" />
        <Row label="Red-flag prefixes" value={red} set={setRed} ph="G83.4, G82" />
      </div>
      {error && <p className="mt-2 text-[13px] text-coral">{error}</p>}
      <div className="mt-4 flex gap-2">
        <Button size="sm" loading={busy} disabled={!code.trim()} leadingIcon={<Check size={14} strokeWidth={1.75} />} onClick={save}>Save</Button>
        <Button size="sm" variant="secondary" leadingIcon={<X size={14} strokeWidth={1.75} />} onClick={onCancel}>Cancel</Button>
      </div>
    </section>
  )
}

// ---- Criteria -------------------------------------------------------------------

function CriteriaTab() {
  const [items, setItems] = useState<CriterionItem[] | null>(null)
  const [editable, setEditable] = useState(false)
  const [adding, setAdding] = useState(false)
  const load = useCallback(() => configApi.criteria().then((r) => { setItems(r.criteria); setEditable(r.editable) }).catch(() => {}), [])
  useEffect(() => { load() }, [load])

  if (items === null) return <p className="text-[13px] text-ink-faint">Loading…</p>
  return (
    <div>
      {!editable && <ReadOnlyNote />}
      <div className="space-y-3">
        {items.map((c) => <CriterionCard key={c.slug} item={c} editable={editable} onChanged={load} />)}
        {adding
          ? <CriterionForm isNew onDone={() => { setAdding(false); load() }} onCancel={() => setAdding(false)} />
          : editable && <Button variant="secondary" size="sm" leadingIcon={<Plus size={14} strokeWidth={1.75} />} onClick={() => setAdding(true)}>Add criterion</Button>}
      </div>
    </div>
  )
}

function CriterionCard({ item, editable, onChanged }: { item: CriterionItem; editable: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  if (editing) return <CriterionForm initial={item} isNew={false} onDone={() => { setEditing(false); onChanged() }} onCancel={() => setEditing(false)} />
  const del = async () => { setBusy(true); try { await configApi.deleteCriterion(item.slug); onChanged() } finally { setBusy(false) } }
  return (
    <section className="rounded-md border border-line bg-paper p-4">
      <div className="mb-1 flex items-center justify-between gap-3">
        <Badge tone="ink">{item.slug}</Badge>
        {editable && (
          <div className="flex items-center gap-1">
            <button onClick={() => setEditing(true)} className="rounded-sm p-1.5 text-ink-faint hover:bg-sunk hover:text-pine" aria-label="Edit"><Pencil size={14} strokeWidth={1.75} /></button>
            <button onClick={del} disabled={busy} className="rounded-sm p-1.5 text-ink-faint hover:bg-sunk hover:text-coral" aria-label="Delete"><Trash2 size={14} strokeWidth={1.75} /></button>
          </div>
        )}
      </div>
      <p className="text-[13px] text-ink-soft">{item.text}</p>
    </section>
  )
}

function CriterionForm({ initial, isNew, onDone, onCancel }: { initial?: CriterionItem; isNew: boolean; onDone: () => void; onCancel: () => void }) {
  const [slug, setSlug] = useState(initial?.slug ?? '')
  const [text, setText] = useState(initial?.text ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const save = async () => {
    setBusy(true); setError(null)
    try { await configApi.saveCriterion({ slug: slug.trim(), text: text.trim() }); onDone() }
    catch (e) { setError(String((e as Error)?.message || e)) } finally { setBusy(false) }
  }
  return (
    <section className="rounded-md border border-pine/30 bg-pine/[0.03] p-4">
      <label className="block">
        <span className="mb-1 block font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">Slug</span>
        <Input value={slug} disabled={!isNew} onChange={(e) => setSlug(e.target.value)} placeholder="mri_lumbar" />
      </label>
      <label className="mt-3 block">
        <span className="mb-1 block font-mono text-[10px] uppercase tracking-[0.12em] text-ink-faint">Criterion text</span>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
          className="w-full rounded-sm border border-line bg-paper px-3 py-2 text-[14px] text-ink placeholder:text-ink-faint focus-visible:border-pine/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/30"
          placeholder="Advanced imaging is medically necessary when…" />
      </label>
      {error && <p className="mt-2 text-[13px] text-coral">{error}</p>}
      <div className="mt-3 flex gap-2">
        <Button size="sm" loading={busy} disabled={!slug.trim() || !text.trim()} leadingIcon={<Check size={14} strokeWidth={1.75} />} onClick={save}>Save</Button>
        <Button size="sm" variant="secondary" leadingIcon={<X size={14} strokeWidth={1.75} />} onClick={onCancel}>Cancel</Button>
      </div>
    </section>
  )
}
