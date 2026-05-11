#!/usr/bin/env node
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = await readFile(new URL('../src/pages/ChatPage/ChainBubble.tsx', import.meta.url), 'utf8')

assert.match(source, /orderedTasks\.length > 10/)
assert.match(source, /react-window/)
assert.match(source, /<List/)
assert.match(source, /virtualizedTaskWindow \? \(/)
assert.match(source, /rowCount=\{orderedTasks\.length\}/)
assert.match(source, /rowHeight=\{132\}/)
assert.match(source, /Math\.min\(520, orderedTasks\.length \* 132\)/)
assert.match(source, /\) : orderedTasks\.map\(renderTaskNode\)/)
