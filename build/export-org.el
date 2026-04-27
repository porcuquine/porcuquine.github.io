(require 'org)
(require 'ox-html)

(setq org-export-with-author nil
      org-export-with-creator nil
      org-export-time-stamp-file nil
      org-html-doctype "html5"
      org-html-html5-fancy t
      org-html-postamble nil
      org-html-preamble nil
      org-html-validation-link nil)

(defun pq/export-org-file (file)
  "Export FILE to HTML with minimal site-wide defaults."
  (let* ((source (expand-file-name file))
         (output-dir (or (getenv "OUTPUT_DIR") default-directory))
         (output (expand-file-name
                  (concat (file-name-base source) ".html")
                  output-dir)))
    (with-current-buffer (find-file-noselect source)
      (let ((org-export-with-author nil)
            (org-export-with-creator nil)
            (org-export-time-stamp-file nil)
            (org-html-doctype "html5")
            (org-html-html5-fancy t)
            (org-html-postamble nil)
            (org-html-preamble nil)
            (org-html-validation-link nil))
        (make-directory output-dir t)
        (let ((output (org-export-to-file 'html output nil nil nil nil nil)))
          (with-temp-buffer
            (insert-file-contents output)
            (goto-char (point-min))
            (while (re-search-forward
                    "^<meta name=\"generator\" content=\"Org Mode\" />\n?" nil t)
              (replace-match ""))
            (write-region nil nil output nil 'silent))
          output)))))

(let ((files command-line-args-left))
  (unless files
    (error "No Org files provided"))
  (dolist (file files)
    (pq/export-org-file file)))
