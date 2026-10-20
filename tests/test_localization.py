"""Ensure newly added worker messages cannot silently lose their English translation."""
import ast
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class LocalizationCoverageTests(unittest.TestCase):
    def test_all_worker_messages_have_translations(self):
        entries = json.loads((ROOT/'Sources/NSMac/Resources/Localizable.json').read_text())
        translated = {entry['source'] for entry in entries}
        missing = []
        class Messages(ast.NodeVisitor):
            def check(self, value):
                if re.search('[\u4e00-\u9fff]',value) and value not in translated and value+'{0}' not in translated:
                    missing.append(value)
            def visit_Constant(self,node):
                if isinstance(node.value,str): self.check(node.value)
            def visit_JoinedStr(self,node):
                template=''; index=0
                for item in node.values:
                    if isinstance(item,ast.Constant): template+=item.value
                    else:
                        template+='{'+str(index)+'}';index+=1
                        self.visit(item.value)
                self.check(template)
        for path in (ROOT/'Worker').glob('*.py'):
            Messages().visit(ast.parse(path.read_text()))
        self.assertEqual(missing,[])

if __name__=='__main__': unittest.main()
