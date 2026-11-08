import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from audio_classification_claim_audit import phrases
from audio_classification_claim_audit.audit import evidence, match_phrases, claims, scan, main

POSITIVE = ('audio classification', 'audio-classification', 'audioclassification', 'audio classification model', 'audio classification models', 'audio classification system', 'audio classification systems', 'audio classification feature', 'audio classification capability', 'audio classification support', 'supports audio classification', 'audio classification tool', 'audio classification api', 'audio classification pipeline', 'audio classification algorithm', 'audio classification library', 'audio classification framework', 'audio classification service', 'audio classification function', 'audio classification engine', 'audio classification engines', 'audio classifier', 'audio classifiers', 'classifies audio', 'classify audio', 'classifies audio clips', 'classify audio clips', 'classifies sounds', 'classify sounds', 'sound classification', 'sound-classification', 'sound classifier', 'sound classifiers', 'classifies sound', 'classify sound', 'audio clip classification', 'audio clip classifier', 'audio classification task', 'audio classification benchmark', 'automatic audio classification', 'automated audio classification', 'classifies audio files', 'classify audio files', 'audio classification software', 'audio classification app', 'audio classification program', 'classifies your audio', 'classify my audio', 'audio scene classification', 'acoustic scene classification')
NEGATIVE = ('does not support audio classification', 'do not support audio classification', "doesn't support audio classification", "don't support audio classification", 'no audio classification', 'without audio classification', 'never performs audio classification', 'does not perform audio classification', 'audio classification not supported', 'audio classification unsupported', 'no audio classification support', 'lacks audio classification', 'missing audio classification', 'audio classification disabled', 'no audio classification capability', 'without audio classification support', 'does not provide audio classification', 'no audio classification model', 'audio classification not available', 'does not use audio classification', 'no audio classifier', 'without audio classifier', 'does not support audio classifier', 'no sound classifier')
GENERIC = ('classify_audio', 'audio_classification', 'classify_sound', 'audio_classifier', 'predict_audio_class', 'audio_classify', 'classify_audio_clip', 'audio_clip_classification', 'classify_audio_file', 'predict_sound_class', 'sound_classification', 'sound_classifier', 'classify_audio_scene', 'audio_scene_classification', 'classify_acoustic_scene', 'predict_audio_label', 'audio_label_prediction', 'audio_classification_model', 'classify_audio_recording', 'audio_recording_classification', 'predict_audio_category', 'audio_category_prediction', 'classify_environmental_sound', 'environmental_sound_classification')
MODELS = ('Wav2Vec2ForSequenceClassification', 'ASTForAudioClassification', 'HubertForSequenceClassification', 'WavLMForSequenceClassification', 'Data2VecAudioForSequenceClassification')

class AuditTests(unittest.TestCase):
    def test_phrase_oracle(self):
        self.assertEqual(POSITIVE, phrases.AUDIOCLASSIFICATION)
        self.assertEqual(NEGATIVE, phrases.NOAUDIOCLASSIFICATION)

    def test_generic_oracle(self):
        self.assertEqual(GENERIC, phrases.GENERIC_NAMES)

    def test_model_oracle(self):
        self.assertEqual(MODELS, phrases.DEDICATED_NAMES)

    def test_span_removal(self):
        self.assertEqual(claims('does not support audio classification'), ([], [NEGATIVE[0]]))

    def test_longest_singular(self):
        self.assertEqual(claims('audio classification model')[0], ['audio classification model'])

    def test_longest_plural(self):
        self.assertEqual(claims('audio classification models')[0], ['audio classification models'])

    def test_collision(self):
        self.assertEqual(claims('classify audio files by date')[0], ['classify audio files'])

    def test_fences(self):
        self.assertEqual(claims('```text\naudio classification\n```'), ([], []))

    def test_inline(self):
        self.assertEqual(claims('`audio classification`')[0], ['audio classification'])

    def fixture(self, files):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for name, text in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return root

    def cli(self, root, *options):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(['audit', str(root)] + list(options))
        return code, out.getvalue(), err.getvalue()

    def test_cli_good(self):
        root = self.fixture({'README.md': POSITIVE[0], 'app.py': 'x.classify_audio(data)'})
        self.assertEqual(self.cli(root)[:2], (0, 'PASS\n'))

    def test_cli_bad_and_case(self):
        root = self.fixture({'README.md': 'AUDIO CLASSIFICATION'})
        code, out, _ = self.cli(root)
        self.assertEqual(code, 2)
        self.assertIn('high: documented-audio-classification-claim-false:', out)

    def test_cli_test_only(self):
        root = self.fixture({'tests/fixture.md': POSITIVE[0]})
        self.assertEqual(self.cli(root)[0], 0)
        self.assertEqual(self.cli(root, '--fail-on', 'medium')[0], 2)
        self.assertEqual(scan(root)[0]['severity'], 'medium')

    def test_cli_denial(self):
        root = self.fixture({'README.md': NEGATIVE[0], 'app.py': 'x.classify_audio(data)'})
        code, out, _ = self.cli(root)
        self.assertEqual(code, 2)
        self.assertIn('high: documented-no-audio-classification-claim-false:', out)

    def test_cli_no_claim(self):
        self.assertEqual(self.cli(self.fixture({'README.md': 'Hello'}))[:2], (0, 'PASS\n'))

    def test_denial_no_source(self):
        self.assertEqual(scan(self.fixture({'README.md': NEGATIVE[0]})), [])

    def test_json(self):
        result = self.cli(self.fixture({'README.md': POSITIVE[0]}), '--json')
        finding = json.loads(result[1])[0]
        self.assertEqual(finding['verdict'], 'FAIL')
        self.assertTrue(finding['message'])

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(['--version'])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(out.getvalue(), '0.1.0\n')

    def test_ignore(self):
        root = self.fixture({'docs/claim.md': POSITIVE[0]})
        self.assertEqual(self.cli(root, '--ignore', 'docs/')[0], 0)

    def test_ignore_before_repo(self):
        root = self.fixture({'docs/claim.md': POSITIVE[0]})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['audit', '--ignore', 'docs/', str(root)]), 0)

    def test_verbose(self):
        result = self.cli(self.fixture({'README.md': 'Hello'}), '--verbose')
        self.assertIn('Scope:', result[2])
        self.assertIn('scan README.md', result[2])

    def test_io_error(self):
        self.assertEqual(self.cli('/nonexistent/audit-fixture')[0], 1)

    def test_usage_error(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(['audit', '--fail-on', 'low'])
        self.assertEqual(caught.exception.code, 1)

    def test_split_modules(self):
        root = self.fixture({'README.md': POSITIVE[0], 'a.py': 'p = pipeline("audio-classification")', 'b.py': 'p(data)'})
        self.assertEqual(self.cli(root)[0], 2)

    def test_excluded_sources(self):
        for folder in ('.git', '__pycache__', '.venv', 'venv'):
            with self.subTest(folder=folder):
                root = self.fixture({'README.md': POSITIVE[0], folder + '/app.py': 'x.classify_audio(data)'})
                self.assertEqual(self.cli(root)[0], 2)

    def test_custom_virtualenv(self):
        root = self.fixture({'README.md': POSITIVE[0], 'custom/pyvenv.cfg': '', 'custom/app.py': 'x.classify_audio(data)'})
        self.assertEqual(self.cli(root)[0], 2)

    def test_readme_self_audit(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(claims((root / 'README.md').read_text()), ([], []))
        self.assertEqual(scan(self.fixture({'README.md': (root / 'README.md').read_text()})), [])


def add_case(name, source, expected):
    def test(self):
        self.assertEqual(evidence(source), expected, source)
    setattr(AuditTests, 'test_' + name, test)


for index, prefix in enumerate(('', 'import transformers\n', 'from transformers import pipeline as p\n', 'import transformers as t\n', 'from vendor import helpers as h\n')):
    func = ('pipeline', 'transformers.pipeline', 'p', 't.pipeline', 'h.pipeline')[index]
    for task_index, task in enumerate(('"audio-classification"', 'task="audio-classification"')):
        for chained in (False, True):
            source = prefix + (func + '(' + task + ')(data)' if chained else 'p1 = ' + func + '(' + task + ')\np1(data)')
            add_case('pipeline_%s_%s_%s' % (index, task_index, chained), source, True)

for index, model in enumerate(MODELS):
    for form, suffix in enumerate(('(data)', '.forward(data)', '.__call__(data)')):
        add_case('model_assigned_%s_%s' % (index, form), 'from transformers import ' + model + ' as M\nm = M.from_pretrained("x")\nm' + suffix, True)
        add_case('model_chained_%s_%s' % (index, form), model + '()' + suffix, True)
    add_case('model_shadow_%s' % index, 'class ' + model + ': pass\nm = ' + model + '()\nm(data)', False)
    add_case('model_lone_%s' % index, model + '()', False)

for index, name in enumerate(GENERIC):
    add_case('generic_attribute_%s' % index, 'arbitrary.' + name + '(data)', True)
    add_case('generic_import_%s' % index, 'from vendor import ' + name + '\n' + name + '(data)', True)
    add_case('generic_alias_%s' % index, 'from vendor import ' + name + ' as f\nf(data)', True)
    add_case('generic_shadow_%s' % index, 'from vendor import ' + name + '\ndef ' + name + '(x): pass\n' + name + '(data)', False)

REJECTIONS = (
    'import transformers, torchaudio, librosa, sklearn',
    'p = pipeline("sound-event-detection")\np(data)',
    'm = SoundEventDetectionModel()\nm(data)',
    'p = pipeline("speech-emotion-recognition")\np(data)',
    'm = EmotionModel()\nm(data)',
    'x.classify_genre(data)', 'x.classify_instrument(data)',
    'x.detect_keyword(data)', 'x.transcribe(data)',
    'p = pipeline("automatic-speech-recognition")\np(data)',
    'librosa.load("file.wav")', 'torchaudio.load("file.wav")',
    'wave.open("file.wav")', 'x.fingerprint(data)',
    'pipeline("audio-classification")', 'classifier(data)',
    '"audio classification"\n# audio classifier',
    'from vendor import classify_audio\nclassify_audio',
    'import subprocess\nsubprocess.run(["audio-classification", "file.wav"])',
    'def pipeline(x): pass\np = pipeline("audio-classification")\np(data)',
    'p = pipeline("text-classification")\np(data)',
    'classify_audio(data)',
)
for index, source in enumerate(REJECTIONS):
    add_case('rejection_%s' % index, source, False)

if __name__ == '__main__':
    unittest.main()
