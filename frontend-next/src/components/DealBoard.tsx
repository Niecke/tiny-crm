import { Link } from '@tanstack/react-router'
import {
  Button as AriaButton,
  DropIndicator,
  GridList,
  GridListItem,
  isTextDropItem,
  Menu,
  MenuItem,
  MenuTrigger,
  Popover,
  useDragAndDrop,
} from 'react-aria-components'
import type { DealRead } from '../api/types'
import { type Stage, stageLabel, stageOptions, valueSummary } from '../deals'
import { formatDay } from '../format'

const DEAL_TYPE = 'application/x-tinycrm-deal'

// The pipeline as columns (#13). A card moves by dragging it to another
// column — mouse, touch, or the keyboard (focus a card, Enter to pick it up,
// Tab to a column, Enter to drop) — or with its "Move to…" menu, which is the
// plain way on a phone. Each column is a React Aria GridList, which brings the
// keyboard and screen-reader support for both.
export function DealBoard({
  deals,
  columns,
  onMove,
  pendingId,
}: {
  deals: DealRead[]
  columns: Stage[]
  onMove: (deal: DealRead, stage: Stage) => void
  pendingId?: string
}) {
  return (
    <div className="board" role="region" aria-label="Pipeline board">
      {columns.map((stage) => (
        <Column
          key={stage}
          stage={stage}
          deals={deals.filter((d) => d.stage === stage)}
          all={deals}
          onMove={onMove}
          pendingId={pendingId}
        />
      ))}
    </div>
  )
}

function Column({
  stage,
  deals,
  all,
  onMove,
  pendingId,
}: {
  stage: Stage
  deals: DealRead[]
  all: DealRead[]
  onMove: (deal: DealRead, stage: Stage) => void
  pendingId?: string
}) {
  const dropped = async (items: Parameters<typeof isTextDropItem>[0][]) => {
    for (const item of items.filter(isTextDropItem)) {
      const id = await item.getText(DEAL_TYPE)
      const deal = all.find((d) => d.id === id)
      if (deal) onMove(deal, stage)
    }
  }

  const { dragAndDropHooks } = useDragAndDrop({
    getItems: (keys) => [...keys].map((key) => ({ [DEAL_TYPE]: String(key), 'text/plain': String(key) })),
    acceptedDragTypes: [DEAL_TYPE],
    getDropOperation: () => 'move',
    // Order inside a column is by expected close date, not by hand, so any
    // drop onto a column — between cards or on its empty space — is a move to
    // its stage.
    onRootDrop: (e) => dropped(e.items),
    onInsert: (e) => dropped(e.items),
    onItemDrop: (e) => dropped(e.items),
    renderDropIndicator: (target) => <DropIndicator target={target} className="board-drop" />,
  })

  const label = stageLabel(stage)
  return (
    <section className="board-column" data-stage={stage} aria-label={label}>
      <h2 className="board-heading">
        {label} <span className="tab-count">{deals.length}</span>
      </h2>
      <GridList
        aria-label={`${label} deals`}
        items={deals}
        dragAndDropHooks={dragAndDropHooks}
        className="board-list"
        renderEmptyState={() => <span className="board-empty">Drop a deal here</span>}
      >
        {(d) => (
          <GridListItem id={d.id} textValue={d.title} className="board-card" data-pending={d.id === pendingId || undefined}>
            <DealCard deal={d} onMove={onMove} />
          </GridListItem>
        )}
      </GridList>
    </section>
  )
}

function DealCard({ deal: d, onMove }: { deal: DealRead; onMove: (deal: DealRead, stage: Stage) => void }) {
  const value = valueSummary(d)
  const who = d.organization_name ?? d.contact_name
  return (
    <div className="board-card-body">
      <AriaButton slot="drag" className="board-grip" aria-label={`Drag ${d.title}`}>
        ⋮⋮
      </AriaButton>
      <div className="row-main">
        <Link to="/deals/$dealId" params={{ dealId: d.id }} className="row-link board-title">
          {d.title}
        </Link>
        {who && <span className="row-meta">{who}</span>}
        {value && <span className="board-value">{value}</span>}
        {d.expected_close_date && <span className="row-meta">by {formatDay(d.expected_close_date)}</span>}
      </div>
      <MenuTrigger>
        <AriaButton className="board-menu" aria-label={`Move ${d.title} to another stage`}>
          ⇄
        </AriaButton>
        <Popover className="popover menu-popover">
          <Menu className="listbox" onAction={(key) => onMove(d, key as Stage)}>
            {stageOptions
              .filter((o) => o.value !== d.stage)
              .map((o) => (
                <MenuItem key={o.value} id={o.value} className="listbox-item">
                  Move to {o.label}
                </MenuItem>
              ))}
          </Menu>
        </Popover>
      </MenuTrigger>
    </div>
  )
}
