import ReactMarkdown from 'react-markdown'

// Notes and descriptions are written in Markdown. Raw HTML in them is dropped,
// not rendered, and links open in a new tab; react-markdown builds React
// elements, so nothing goes through innerHTML.
export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        skipHtml
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
