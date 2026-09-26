import { type CalendarDate, type CalendarDateTime, parseDate, parseDateTime } from '@internationalized/date'
import {
  Button,
  Calendar,
  CalendarCell,
  CalendarGrid,
  DateInput,
  DatePicker as AriaDatePicker,
  DateSegment,
  Dialog,
  FieldError,
  Group,
  Heading,
  Label,
  Popover,
  Text,
} from 'react-aria-components'

// A date, or with `withTime` a date and time: typed segment by segment in the
// browser's locale order, or the day picked from a calendar. The value is a
// plain string — "YYYY-MM-DD", or "YYYY-MM-DDTHH:mm" in local time — and ""
// for none, so a form field holds a string.
export function DatePicker({
  label,
  value,
  onChange,
  description,
  errorMessage,
  minValue,
  maxValue,
  withTime,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  description?: string
  errorMessage?: string
  minValue?: string
  maxValue?: string
  withTime?: boolean
}) {
  const toValue = withTime ? toDateTime : toDate
  const parsed = toValue(value)
  return (
    <AriaDatePicker
      className="field"
      value={parsed}
      onChange={(d) => onChange(d ? d.toString().slice(0, withTime ? 16 : 10) : '')}
      minValue={toValue(minValue)}
      maxValue={toValue(maxValue)}
      isInvalid={Boolean(errorMessage)}
      validationBehavior="aria"
      granularity={withTime ? 'minute' : 'day'}
      hourCycle={24}
    >
      <Label className="field-label">{label}</Label>
      <Group className="input date-group">
        <DateInput className="date-input">
          {(segment) => <DateSegment segment={segment} className="date-segment" />}
        </DateInput>
        {value && (
          <Button className="date-clear" aria-label={`Clear ${label.toLowerCase()}`} onPress={() => onChange('')}>
            ×
          </Button>
        )}
        <Button className="date-button" aria-label={`Pick ${label.toLowerCase()} from a calendar`}>
          <span aria-hidden="true">▾</span>
        </Button>
      </Group>
      {description && !errorMessage && (
        <Text slot="description" className="field-description">
          {description}
        </Text>
      )}
      <FieldError className="field-error">{errorMessage}</FieldError>
      <Popover className="popover calendar-popover" offset={4}>
        <Dialog className="calendar-dialog">
          <Calendar className="calendar">
            <header className="calendar-header">
              <Button slot="previous" className="button button-quiet">
                ‹
              </Button>
              <Heading className="calendar-heading" />
              <Button slot="next" className="button button-quiet">
                ›
              </Button>
            </header>
            <CalendarGrid className="calendar-grid">
              {(date) => <CalendarCell date={date} className="calendar-cell" />}
            </CalendarGrid>
          </Calendar>
        </Dialog>
      </Popover>
    </AriaDatePicker>
  )
}

// A malformed string is treated as no date rather than thrown on: the value
// comes from the API or from this component, so it only happens to old data.
function toDate(value: string | undefined): CalendarDate | null | undefined {
  if (value === undefined) return undefined
  if (!value) return null
  try {
    return parseDate(value.slice(0, 10))
  } catch {
    return null
  }
}

function toDateTime(value: string | undefined): CalendarDateTime | null | undefined {
  if (value === undefined) return undefined
  if (!value) return null
  try {
    return parseDateTime(value.slice(0, 16))
  } catch {
    return null
  }
}
