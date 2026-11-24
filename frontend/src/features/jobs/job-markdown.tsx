import Markdown from "react-markdown";

export function JobMarkdown({ text }: { text: string }) {
  return (
    <div className="jobs-markdown">
      <Markdown skipHtml disallowedElements={["img"]}>
        {text}
      </Markdown>
    </div>
  );
}
