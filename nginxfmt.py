#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This Python script formats nginx configuration files in consistent way.

Originally published under https://github.com/1connect/nginx-config-formatter,
then moved to https://github.com/slomkowski/nginx-config-formatter.
"""

import argparse
import codecs
import dataclasses
import logging
import pathlib
import re

__author__ = "Michał Słomkowski"
__license__ = "Apache 2.0"
__version__ = "1.2.0-SNAPSHOT"

"""Class holds the formatting options. For now, only indentation supported."""


@dataclasses.dataclass
class FormatterOptions:
    indentation: int = 4


class Formatter:
    _TEMPLATE_VARIABLE_OPENING_TAG = '___TEMPLATE_VARIABLE_OPENING_TAG___'
    _TEMPLATE_VARIABLE_CLOSING_TAG = '___TEMPLATE_VARIABLE_CLOSING_TAG___'

    _TEMPLATE_BRACKET_OPENING_TAG = '___TEMPLATE_BRACKET_OPENING_TAG___'
    _TEMPLATE_BRACKET_CLOSING_TAG = '___TEMPLATE_BRACKET_CLOSING_TAG___'

    def __init__(self,
                 options: FormatterOptions = FormatterOptions(),
                 logger: logging.Logger = None):
        self.logger = logger if logger is not None else logging.getLogger(__name__)
        self.options = options

    @staticmethod
    def _strip_line(single_line):
        """Strips the line and replaces neighbouring whitespaces with single space (except when within quotation
        marks). """
        single_line = single_line.strip()
        if single_line.startswith('#'):
            return single_line

        within_quotes = False
        parts = []
        for part in re.split('"', single_line):
            if within_quotes:
                parts.append(part)
            else:
                parts.append(re.sub(r'[\s]+', ' ', part))
            within_quotes = not within_quotes
        return '"'.join(parts)

    @staticmethod
    def _count_multi_semicolon(single_line):
        """count multi_semicolon (except when within quotation marks)."""
        single_line = single_line.strip()
        if single_line.startswith('#'):
            return 0, 0

        within_quotes = False
        q = 0
        c = 0
        for part in re.split('"', single_line):
            if within_quotes:
                q = 1
            else:
                c += part.count(';')
            within_quotes = not within_quotes
        return q, c

    @staticmethod
    def multi_semicolon(single_line):
        """break multi_semicolon into multiline (except when within quotation marks)."""
        single_line = single_line.strip()
        if single_line.startswith('#'):
            return single_line

        within_quotes = False
        parts = []
        for part in re.split('"', single_line):
            if within_quotes:
                parts.append(part)
            else:
                parts.append(part.replace(";", ";\n"))
            within_quotes = not within_quotes
        return '"'.join(parts)

    def apply_variable_template_tags(self, line: str) -> str:
        """Replaces variable indicators ${ and } with tags, so subsequent formatting is easier."""
        return re.sub(r'\${\s*(\w+)\s*}',
                      self._TEMPLATE_VARIABLE_OPENING_TAG + r"\1" + self._TEMPLATE_VARIABLE_CLOSING_TAG,
                      line,
                      flags=re.UNICODE)

    def strip_variable_template_tags(self, line: str) -> str:
        """Replaces tags back with ${ and } respectively."""
        return re.sub(self._TEMPLATE_VARIABLE_OPENING_TAG + r'\s*(\w+)\s*' + self._TEMPLATE_VARIABLE_CLOSING_TAG,
                      r'${\1}',
                      line,
                      flags=re.UNICODE)

    def apply_bracket_template_tags(self, lines: list) -> list:
        """ Replaces bracket { and } with tags, so subsequent formatting is easier."""
        formatted_lines = []

        for line in lines:
            formatted_line = ""
            in_quotes = False
            last_char = ""

            if line.startswith('#'):
                formatted_line += line
            else:
                for char in line:
                    if (char == "\'" or char == "\"") and last_char != "\\":
                        in_quotes = self.reverse_in_quotes_status(in_quotes)

                    if in_quotes:
                        if char == "{":
                            formatted_line += self._TEMPLATE_BRACKET_OPENING_TAG
                        elif char == "}":
                            formatted_line += self._TEMPLATE_BRACKET_CLOSING_TAG
                        else:
                            formatted_line += char
                    else:
                        formatted_line += char

                    last_char = char

            formatted_lines.append(formatted_line)

        return formatted_lines

    @staticmethod
    def reverse_in_quotes_status(status: bool) -> bool:
        if status:
            return False
        return True

    def strip_bracket_template_tags(self, content: str) -> str:
        """ Replaces tags back with { and } respectively."""
        content = content.replace(self._TEMPLATE_BRACKET_OPENING_TAG, "{", -1)
        content = content.replace(self._TEMPLATE_BRACKET_CLOSING_TAG, "}", -1)
        return content

    def clean_lines(self, orig_lines) -> list:
        """Strips the lines and splits them if they contain curly brackets."""
        cleaned_lines = []
        for line in orig_lines:
            line = self._strip_line(line)
            line = self.apply_variable_template_tags(line)
            if line == "":
                cleaned_lines.append("")
                continue
            else:
                if line.startswith("#"):
                    cleaned_lines.append(self.strip_variable_template_tags(line))
                else:
                    q, c = self._count_multi_semicolon(line)
                    if q == 1 and c > 1:
                        ml = self.multi_semicolon(line)
                        cleaned_lines.extend(self.clean_lines(ml.splitlines()))
                    elif q != 1 and c > 1:
                        newlines = line.split(";")
                        cleaned_lines.extend(self.clean_lines(["".join([ln, ";"]) for ln in newlines if ln != ""]))
                    else:
                        if line.startswith("rewrite"):
                            cleaned_lines.append(self.strip_variable_template_tags(line))
                        else:
                            cleaned_lines.extend(
                                [self.strip_variable_template_tags(ln).strip() for ln in re.split(r"([{}])", line) if
                                 ln != ""])
        return cleaned_lines

    @staticmethod
    def _join_opening_bracket(lines):
        """When opening curly bracket is in it's own line (K&R convention), it's joined with precluding line (Java)."""
        modified_lines = []
        for i in range(len(lines)):
            if i > 0 and lines[i] == "{":
                modified_lines[-1] += " {"
            else:
                modified_lines.append(lines[i])
        return modified_lines

    def _perform_indentation(self, lines):
        """Indents the lines according to their nesting level determined by curly brackets."""
        indented_lines = []
        current_indent = 0
        indentation_str = ' ' * self.options.indentation
        for line in lines:
            if not line.startswith("#") and line.endswith('}') and current_indent > 0:
                current_indent -= 1

            if line != "":
                indented_lines.append(current_indent * indentation_str + line)
            else:
                indented_lines.append("")

            if not line.startswith("#") and line.endswith('{'):
                current_indent += 1

        return indented_lines

    def format_string(self,
                      contents: str):
        """Accepts the string containing nginx configuration and returns formatted one. Adds newline at the end."""
        lines = contents.splitlines()
        lines = self.apply_bracket_template_tags(lines)
        lines = self.clean_lines(lines)
        lines = self._join_opening_bracket(lines)
        lines = self._perform_indentation(lines)

        text = '\n'.join(lines)
        text = self.strip_bracket_template_tags(text)

        for pattern, substitute in ((r'\n{3,}', '\n\n\n'), (r'^\n', ''), (r'\n$', '')):
            text = re.sub(pattern, substitute, text, re.MULTILINE)

        return text + '\n'

    def format_file(self,
                    file_path: pathlib.Path,
                    original_backup_file_path: pathlib.Path = None):
        """
        Performs the formatting on the given file. The function tries to detect file encoding first.
        :param file_path: path to original nginx configuration file. This file will be overridden.
        :param original_backup_file_path: optional path, where original file will be backed up.
        """
        encodings = ('utf-8', 'latin1')

        encoding_failures = []
        chosen_encoding = None
        original_file_content = None

        for enc in encodings:
            try:
                with codecs.open(file_path, 'r', encoding=enc) as rfp:
                    original_file_content = rfp.read()
                chosen_encoding = enc
                break
            except ValueError as e:
                encoding_failures.append(e)

        if chosen_encoding is None:
            raise Exception('none of encodings %s are valid for file %s. Errors: %s'
                            % (encodings, file_path, [e.message for e in encoding_failures]))

        assert original_file_content is not None

        with codecs.open(file_path, 'w', encoding=chosen_encoding) as wfp:
            wfp.write(self.format_string(original_file_content))

        self.logger.info("Formatted file '%s' (detected encoding %s).", file_path, chosen_encoding)

        if original_backup_file_path:
            with codecs.open(original_backup_file_path, 'w', encoding=chosen_encoding) as wfp:
                wfp.write(original_file_content)
            self.logger.info("Original saved to '%s'.", original_backup_file_path)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description=__doc__)

    # todo add logger: logs to stderr
    # option to format from stdin

    arg_parser.add_argument("-v", "--verbose", action="store_true", help="show formatted file names")
    arg_parser.add_argument("-b", "--backup-original", action="store_true", help="backup original config file")
    arg_parser.add_argument("-i", "--indent", action="store", default=4, type=int,
                            help="specify number of spaces for indentation")
    arg_parser.add_argument("config_files", nargs='+', help="configuration files to format")

    args = arg_parser.parse_args()

    format_options = FormatterOptions()
    format_options.indentation = args.indent
    formatter = Formatter(format_options)

    for config_file_path in args.config_files:
        backup_file_path = config_file_path + '~' if args.backup_original else None
        formatter.format_file(config_file_path, backup_file_path)
