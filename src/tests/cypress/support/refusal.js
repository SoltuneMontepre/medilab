export function assertNoPriorRefusal(displayedMessage, message) {
  expect(displayedMessage, "no refusal is left from an earlier action").not.to.include(message);
}

export function assertRefusalOutcome({ displayedMessage, message, before, after }) {
  expect(displayedMessage, "displayed refusal").to.include(message);
  expect(after, "record after refusal").to.deep.equal(before);
}
