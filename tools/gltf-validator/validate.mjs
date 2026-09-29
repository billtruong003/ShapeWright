// Usage: node validate.mjs <file.glb>  -> prints the validator's JSON report issues
import { readFileSync } from "node:fs";
import validator from "gltf-validator";

const path = process.argv[2];
const report = await validator.validateBytes(new Uint8Array(readFileSync(path)), {
  maxIssues: 50,
  ignoredIssues: ["UNUSED_OBJECT"],
});
const { numErrors, numWarnings, numInfos, numHints, messages } = report.issues;
console.log(JSON.stringify({ numErrors, numWarnings, numInfos, numHints, messages }));
