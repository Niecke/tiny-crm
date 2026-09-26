import { zodResolver } from '@hookform/resolvers/zod'
import type { ReactNode } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import type { DealCreate, DealRead } from '../api/types'
import { formatMoney, isDecided, stageOptions, unitOptions, valueTypeOptions } from '../deals'
import { ContactPicker, OrganizationPicker } from './RecordPickers'
import { Button } from './ui/Button'
import { DatePicker } from './ui/DatePicker'
import { FormTextField } from './ui/FormTextField'
import { Segmented } from './ui/Segmented'
import { Select } from './ui/Select'

const optional = z.string().trim()
// Up to 12 digits and 2 decimals (schemas/common.py Money); a comma is what a
// German keyboard types for the point.
const money = optional.refine((v) => v === '' || /^\d{1,12}([.,]\d{1,2})?$/.test(v), 'An amount like 12000 or 850.50.')
const toDecimal = (v: string) => (v ? v.replace(',', '.') : null)

type ValueType = (typeof valueTypeOptions)[number]['value']
type Unit = (typeof unitOptions)[number]['value']

const formSchema = z
  .object({
    title: z.string().trim().min(1, 'Title is required.'),
    value_type: z.enum(['fixed', 'rate_based', 'retainer']),
    fixed_value: money,
    rate: money,
    rate_unit: z.enum(['', 'hour', 'day', 'week', 'month']),
    estimated_volume: money,
    volume_unit: z.enum(['', 'hour', 'day', 'week', 'month']),
    currency: optional.refine((v) => /^[A-Za-z]{3}$/.test(v), 'Three letters, like EUR.'),
    stage: z.enum(stageOptions.map((o) => o.value) as [string, ...string[]]),
    lost_reason: optional,
    expected_close_date: z.string(),
    probability: optional.refine(
      (v) => v === '' || (/^\d{1,3}$/.test(v) && Number(v) <= 100),
      'A whole percentage from 0 to 100.',
    ),
    contact_id: z.string().nullable(),
    organization_id: z.string().nullable(),
    notes: optional,
  })
  // The router's pricing rules, reported on the field.
  .refine((v) => v.value_type === 'fixed' || !v.rate || v.rate_unit, {
    path: ['rate_unit'],
    message: 'Per what?',
  })
  .refine((v) => v.value_type === 'fixed' || !v.estimated_volume || v.volume_unit, {
    path: ['volume_unit'],
    message: 'In what?',
  })

type FormInput = z.input<typeof formSchema>
type FormOutput = z.output<typeof formSchema>

// Every field is sent. The ones that do not belong to the chosen pricing are
// sent as null, so switching a deal from fixed to a day rate clears the old
// contract sum rather than leaving it behind; a lost reason goes only with a
// lost deal.
const toBody = (v: FormOutput): DealCreate => {
  const rated = v.value_type !== 'fixed'
  return {
    title: v.title,
    value_type: v.value_type,
    fixed_value: rated ? null : toDecimal(v.fixed_value),
    rate: rated ? toDecimal(v.rate) : null,
    rate_unit: rated && v.rate ? (v.rate_unit as Unit) : null,
    estimated_volume: rated ? toDecimal(v.estimated_volume) : null,
    volume_unit: rated && v.estimated_volume ? (v.volume_unit as Unit) : null,
    currency: v.currency.toUpperCase(),
    stage: v.stage as DealCreate['stage'],
    lost_reason: v.stage === 'lost' ? v.lost_reason || null : null,
    expected_close_date: v.expected_close_date || null,
    probability: v.probability === '' ? null : Number(v.probability),
    contact_id: v.contact_id,
    organization_id: v.organization_id,
    notes: v.notes || null,
  }
}

const toDefaults = (d: DealRead | undefined, preset: DealPreset): FormInput => ({
  title: d?.title ?? '',
  value_type: d?.value_type ?? 'fixed',
  fixed_value: d?.fixed_value ?? '',
  rate: d?.rate ?? '',
  rate_unit: d?.rate_unit ?? '',
  estimated_volume: d?.estimated_volume ?? '',
  volume_unit: d?.volume_unit ?? '',
  currency: d?.currency ?? 'EUR',
  stage: d?.stage ?? 'lead',
  lost_reason: d?.lost_reason ?? '',
  expected_close_date: d?.expected_close_date ?? '',
  probability: d?.probability != null ? String(d.probability) : '',
  contact_id: d ? (d.contact_id ?? null) : (preset.contact?.id ?? null),
  organization_id: d ? (d.organization_id ?? null) : (preset.organization?.id ?? null),
  notes: d?.notes ?? '',
})

export type DealPreset = {
  contact?: { id: string; name: string }
  organization?: { id: string; name: string }
}

const unitSelect = unitOptions.map((u) => ({ value: u.value, label: u.label }))

export function DealForm({
  initial,
  preset = {},
  onSubmit,
  submitLabel,
  pending,
  error,
  cancel,
}: {
  initial?: DealRead
  preset?: DealPreset
  onSubmit: (body: DealCreate) => void
  submitLabel: string
  pending: boolean
  error: Error | null
  cancel: ReactNode
}) {
  const { control, handleSubmit, setValue, getValues } = useForm<FormInput, unknown, FormOutput>({
    resolver: zodResolver(formSchema),
    defaultValues: toDefaults(initial, preset),
  })
  const [valueType, stage, rate, rateUnit, volume, volumeUnit, currency] = useWatch({
    control,
    name: ['value_type', 'stage', 'rate', 'rate_unit', 'estimated_volume', 'volume_unit', 'currency'],
  })
  const rated = valueType !== 'fixed'
  const decided = isDecided(stage)

  // How the total will come out, as the database computes it: rate × volume
  // when the units agree, nothing when they do not.
  let hint: string | null = null
  if (rated && rate && rateUnit) {
    const unit = unitOptions.find((u) => u.value === rateUnit)
    if (!volume) hint = 'No volume estimate: an open-ended engagement, forecast by its rate.'
    else if (volumeUnit && volumeUnit !== rateUnit)
      hint = `Estimated in ${unitOptions.find((u) => u.value === volumeUnit)?.plural} at a ${unit?.label} rate — no total derived.`
    else if (/^\d+([.,]\d+)?$/.test(rate) && /^\d+([.,]\d+)?$/.test(volume)) {
      const total = (Number(rate.replace(',', '.')) * Number(volume.replace(',', '.'))).toFixed(2)
      hint = `Expected value about ${formatMoney(total, currency.toUpperCase() || 'EUR')}.`
    }
  }

  return (
    <form className="panel form" onSubmit={handleSubmit((values) => onSubmit(toBody(values)))} noValidate>
      <FormTextField control={control} name="title" label="Title" autoFocus />

      <fieldset className="form-section">
        <legend>Value</legend>
        <div className="form-row">
          <Controller
            control={control}
            name="value_type"
            render={({ field }) => (
              <div className="field">
                <span className="field-label" aria-hidden="true">
                  Priced as
                </span>
                <Segmented
                  label="Priced as"
                  value={field.value}
                  onChange={(v: ValueType) => {
                    field.onChange(v)
                    // A rate needs a unit; start from the usual one, and count
                    // the volume in the same unit.
                    if (v !== 'fixed' && !getValues('rate_unit')) {
                      const unit = v === 'retainer' ? 'month' : 'day'
                      setValue('rate_unit', unit)
                      if (!getValues('volume_unit')) setValue('volume_unit', unit)
                    }
                  }}
                  options={valueTypeOptions.map((o) => ({ value: o.value, label: o.label }))}
                />
              </div>
            )}
          />
          <FormTextField control={control} name="currency" label="Currency" maxLength={3} />
        </div>

        {rated ? (
          <>
            <div className="form-row">
              <FormTextField control={control} name="rate" label="Rate" inputMode="decimal" />
              <Controller
                control={control}
                name="rate_unit"
                render={({ field, fieldState }) => (
                  <Select
                    label="Per"
                    options={unitSelect}
                    value={field.value}
                    onChange={(v) => {
                      field.onChange(v)
                      // The volume is usually counted in the unit billed.
                      if (!getValues('volume_unit')) setValue('volume_unit', v)
                    }}
                    errorMessage={fieldState.error?.message}
                  />
                )}
              />
            </div>
            <div className="form-row">
              <FormTextField
                control={control}
                name="estimated_volume"
                label="Estimated volume"
                inputMode="decimal"
                description="Optional. Leave empty for open-ended work."
              />
              <Controller
                control={control}
                name="volume_unit"
                render={({ field, fieldState }) => (
                  <Select
                    label="In"
                    options={unitSelect}
                    value={field.value}
                    onChange={field.onChange}
                    errorMessage={fieldState.error?.message}
                  />
                )}
              />
            </div>
            {hint && <p className="muted small">{hint}</p>}
          </>
        ) : (
          <FormTextField control={control} name="fixed_value" label="Contract sum" inputMode="decimal" />
        )}
      </fieldset>

      <fieldset className="form-section">
        <legend>Pipeline</legend>
        <div className="form-row">
          <Controller
            control={control}
            name="stage"
            render={({ field }) => (
              <Select label="Stage" options={stageOptions} value={field.value as never} onChange={field.onChange} />
            )}
          />
          <FormTextField
            control={control}
            name="probability"
            label="Probability (%)"
            inputMode="numeric"
            isDisabled={decided}
            description={decided ? `Fixed at ${stage === 'lost' ? 0 : 100}% once the deal is decided.` : undefined}
          />
        </div>
        {stage === 'lost' && <FormTextField control={control} name="lost_reason" label="Lost because" rows={2} />}
        <Controller
          control={control}
          name="expected_close_date"
          render={({ field }) => (
            <DatePicker
              label={decided ? 'Was expected to close' : 'Expected close'}
              value={field.value}
              onChange={field.onChange}
              description={field.value ? undefined : 'No forecast.'}
            />
          )}
        />
      </fieldset>

      <fieldset className="form-section">
        <legend>With</legend>
        <div className="form-row">
          <Controller
            control={control}
            name="organization_id"
            render={({ field }) => (
              <OrganizationPicker
                value={field.value}
                onChange={field.onChange}
                initialLabel={initial?.organization_name ?? preset.organization?.name}
              />
            )}
          />
          <Controller
            control={control}
            name="contact_id"
            render={({ field }) => (
              <ContactPicker
                placeholder="Optional"
                value={field.value}
                onChange={field.onChange}
                initialLabel={initial?.contact_name ?? preset.contact?.name}
              />
            )}
          />
        </div>
        <FormTextField control={control} name="notes" label="Notes" rows={4} />
      </fieldset>

      {error && (
        <p className="form-error" role="alert">
          {error.message}
        </p>
      )}

      <div className="form-actions">
        {cancel}
        <Button type="submit" isDisabled={pending}>
          {pending ? 'Saving…' : submitLabel}
        </Button>
      </div>
    </form>
  )
}
