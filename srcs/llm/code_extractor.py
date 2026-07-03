import re
import json
from srcs.llm.models import (
    ExtractedCodeBlock,
    ExtractedBlockStatus,
    ExtractedBlockFormat,
)


class CodeExtractor:
    """Extract executable Python code from a raw LLM response.

    Tries several tool-calling formats in order (Python code block, XML,
    JSON/Hermes, ReAct) and converts non-Python formats into an equivalent
    Python call. Reasoning tags (<think>, etc.) are stripped first so draft
    code inside them is ignored.
    """

    @classmethod
    def extract(cls, raw_block: str | None) -> ExtractedCodeBlock:
        """Extract code from an LLM response, trying each format in order.

        Strips reasoning tags, then tries the Python, XML, JSON/Hermes and
        ReAct extractors. Returns the first successful ExtractedCodeBlock,
        or a NO_CODE_FOUND block if the input is empty or no format matches.
        """
        extractor_fn = [
            cls._extract_python,
            cls._extract_xml,
            cls.extract_json_hermes,
            cls.extract_react,
        ]

        def _strip_think(text: str) -> str:
            """Remove <think>/<thinking>/<reasoning> blocks and their content.

            Runs before extraction so any draft code inside a reasoning block
            is discarded rather than mistaken for the final answer.
            """
            THINK_PATTERN = r"<(think|thinking|reasoning)>.*?</\1>"
            return re.sub(
                THINK_PATTERN, "", text, flags=re.DOTALL | re.IGNORECASE
            )

        if raw_block is None or not raw_block:
            return ExtractedCodeBlock(
                extracted_block_status=ExtractedBlockStatus.NO_CODE_FOUND,
                extracted_block_format=ExtractedBlockFormat.UNKNOWN,
            )
        clean = _strip_think(raw_block)

        for extractor in extractor_fn:
            result = extractor(clean)
            if result is not None:
                return result

        return ExtractedCodeBlock(
            extracted_block_status=ExtractedBlockStatus.NO_CODE_FOUND,
            extracted_block_format=ExtractedBlockFormat.UNKNOWN,
        )

    @staticmethod
    def _extract_python(raw_block: str) -> ExtractedCodeBlock | None:
        """Extract code from a Markdown ```python block.

        Returns an OK block for a well-closed fence, a MALFORMED_RECOVERED
        block if the closing fence is missing (e.g. cut by the stop token),
        or None if no Python block is present.
        """
        CLOSED = r"```(?:python)?\n?(.*?)```"
        UNCLOSED = r"```(?:python)?\n?(.*)$"

        m = re.search(CLOSED, raw_block, re.DOTALL)
        if m:
            code = m.group(1).strip()
            if code:
                return ExtractedCodeBlock(
                    code_extracted=code,
                    extracted_block_status=ExtractedBlockStatus.OK,
                    extracted_block_format=ExtractedBlockFormat.PYTHON_FORMAT,
                )

        m = re.search(UNCLOSED, raw_block, re.DOTALL)
        if m:
            code = m.group(1).strip().rstrip("`").strip()
            if code:
                return ExtractedCodeBlock(
                    code_extracted=code,
                    extracted_block_status=(
                        ExtractedBlockStatus.MALFORMED_RECOVERED
                    ),
                    extracted_block_format=ExtractedBlockFormat.PYTHON_FORMAT,
                )
        return None

    @staticmethod
    def _args_to_python(name: str, args: dict) -> str:
        """Turn a tool name and args dict into a Python call string.

        Uses repr() for each value so types are rendered correctly, e.g.
        ("read_file", {"path": "/x"}) -> 'result = read_file(path=\\'/x\\')'.
        """
        parts = [f"{k}={v!r}" for k, v in args.items()]
        return f"result = {name}({', '.join(parts)})"

    @staticmethod
    def _extract_xml(raw_block: str) -> ExtractedCodeBlock | None:
        """Extract an XML tool call and convert it to a Python call.

        Parses <invoke name="..."> with its <parameter> children, then
        builds the equivalent Python call. Returns None if no invoke block
        is found.
        """
        invoke_m = re.search(
            r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>',
            raw_block,
            re.DOTALL,
        )

        if not invoke_m:
            return None
        name = invoke_m.group(1)
        body = invoke_m.group(2)
        args = {}
        param_pat = r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>'

        for pm in re.finditer(param_pat, body, re.DOTALL):
            args[pm.group(1)] = pm.group(2).strip()

        code = CodeExtractor._args_to_python(name, args)
        return ExtractedCodeBlock(
            code_extracted=code,
            extracted_block_status=ExtractedBlockStatus.OK,
            extracted_block_format=ExtractedBlockFormat.XML_FORMAT,
        )

    @staticmethod
    def extract_json_hermes(raw_block: str) -> ExtractedCodeBlock | None:
        """Extract a Hermes-style JSON tool call and convert it to Python.

        Parses <tool_call>{"name": ..., "arguments": {...}}</tool_call> and
        builds the equivalent Python call. Returns None if the block is
        missing or the JSON is malformed.
        """
        pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"

        m = re.search(pattern, raw_block, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(1))
            name = data["name"]
            args = data.get("arguments", {})
        except (json.JSONDecodeError, KeyError, TypeError):
            return None
        if not isinstance(name, str) or not isinstance(args, dict):
            return None

        code = CodeExtractor._args_to_python(name, args)

        return ExtractedCodeBlock(
            code_extracted=code,
            extracted_block_status=ExtractedBlockStatus.OK,
            extracted_block_format=ExtractedBlockFormat.JSON_HERMES_FORMAT,
        )

    @staticmethod
    def extract_react(raw_block: str) -> ExtractedCodeBlock | None:
        """Extract a ReAct tool call and convert it to a Python call.

        Reads the `Action:` name and optional `Action Input:` JSON, then
        builds the equivalent Python call. Handles calls with no arguments.
        Returns None if no Action is found.
        """
        name_m = re.search(r"Action:\s*(\w+)", raw_block)

        input_m = re.search(r"Action Input:\s*(\{.*?\})", raw_block, re.DOTALL)
        if not name_m:
            return None
        name = name_m.group(1)
        args = {}
        if input_m:
            try:
                args = json.loads(input_m.group(1))
            except json.JSONDecodeError:
                return None
            if not isinstance(args, dict):
                return None
        code = CodeExtractor._args_to_python(name, args)

        return ExtractedCodeBlock(
            code_extracted=code,
            extracted_block_status=ExtractedBlockStatus.OK,
            extracted_block_format=ExtractedBlockFormat.REACT_FORMAT,
        )
