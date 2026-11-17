package com.koudai.town;

import org.xml.sax.Attributes;
import org.xml.sax.helpers.DefaultHandler;

import java.io.BufferedInputStream;
import java.io.InputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import javax.xml.parsers.SAXParser;
import javax.xml.parsers.SAXParserFactory;

/**
 * .docx 正文提取，**零第三方依赖**。
 *
 * <p>为什么不用 Apache POI：docx 只是一个 ZIP，正文在 {@code word/document.xml}。
 * 我们要的只是"读出文字"，而 POI 带进来的是"完整读写 Word 对象模型"——
 * 十几次 dex 方法数、十几 MB 体积，换来一堆用不到的功能。这里只用 Android
 * 自带的 {@code java.util.zip} + {@code javax.xml.parsers}（SAX）。
 *
 * <p>刻意不引用任何 android.* 类，方便在桌面 JDK 上直接跑单元测试
 * （见 {@code testbed/docx-reader-test/}）。
 *
 * <p>只读正文，不做格式：
 * <ul>
 *   <li>段落 {@code <w:p>} → 换行，同一段里的 {@code <w:tab>} → 制表符、{@code <w:br>} → 换行</li>
 *   <li>表格单元格 {@code <w:tc>} → 以 {@code " | "} 分隔，行 {@code <w:tr>} 结束换行</li>
 *   <li>页眉页脚、脚注、批注、修订、文本框里的文字**不读**（不在 document.xml 主文档流里）</li>
 *   <li>图片、图表、公式只留下空行</li>
 * </ul>
 */
public final class DocxReader {

    /**
     * 正文上限，40 万字符。
     *
     * <p>再长也没有意义：上下文只有 8192 tokens（约 3000 汉字），
     * 上层必须分块处理；而 40 万字符在手机上已经占 800 KB，再多容易 OOM。
     */
    public static final int MAX_CHARS = 400000;

    /** 解析结果。失败时 {@code err != null}，此时 {@code text} 可能是空串。 */
    public static final class Result {
        public String text = "";
        public int paras = 0;
        public boolean truncated = false;
        public String err = null;
    }

    private DocxReader() {
    }

    /** 读一个 .docx。调用方负责关闭 {@code raw}；这里也会关（重复关无害）。 */
    public static Result read(InputStream raw) {
        Result r = new Result();
        BufferedInputStream bin = raw instanceof BufferedInputStream
                ? (BufferedInputStream) raw : new BufferedInputStream(raw);
        ZipInputStream zin = null;
        try {
            // 先看 magic：不是 ZIP 的话 getNextEntry() 只会静默返回 null，
            // 报出来的是"没有正文"，对用户毫无帮助（老 .doc/加密文档/PDF 都是这种情况）
            if (!looksLikeZip(bin)) {
                r.err = "这不是 .docx 文件。老版 .doc 或加密文档，请先在 Word 里另存为 .docx";
                return r;
            }
            zin = new ZipInputStream(bin);
            ZipEntry e;
            int scanned = 0;
            while ((e = zin.getNextEntry()) != null) {
                // 正常的 docx 只有几十个条目；防的是把别的大 zip 拖进来白扫一遍
                if (++scanned > 20000) {
                    r.err = "这个压缩包条目太多，可能不是 Word 文档";
                    return r;
                }
                if (!"word/document.xml".equals(e.getName())) continue;
                parseBody(zin, r);
                return r;
            }
            r.err = "这个文件里没有 Word 正文（可能是空的，或者文件已损坏）";
            return r;
        } catch (Throwable t) {
            if (r.text.length() == 0) r.err = "读取失败：" + msgOf(t);
            return r;
        } finally {
            try {
                if (zin != null) zin.close();
            } catch (Throwable ignore) {
                // 关闭失败不影响已经读到的内容
            }
        }
    }

    /** 读前 4 字节判断是不是 ZIP（docx 的外壳）。读完复位，不消耗调用方的流。 */
    private static boolean looksLikeZip(BufferedInputStream in) {
        try {
            in.mark(8);
            byte[] h = new byte[4];
            int n = 0;
            while (n < 4) {
                int k = in.read(h, n, 4 - n);
                if (k <= 0) break;
                n += k;
            }
            in.reset();
            return n == 4 && h[0] == 'P' && h[1] == 'K' && h[2] == 3 && h[3] == 4;
        } catch (Throwable t) {
            return false;
        }
    }

    /** 解析 {@code word/document.xml}；超长时靠 {@link Stop} 提前中断，不读完整个文件。 */
    private static void parseBody(InputStream in, Result r) {
        final StringBuilder sb = new StringBuilder();
        try {
            SAXParserFactory f = SAXParserFactory.newInstance();
            f.setNamespaceAware(true);
            SAXParser p = f.newSAXParser();
            // docx 是本地文件，但仍然关掉 DOCTYPE：走 XXE 读任意文件没有意义，只有风险
            try {
                p.getXMLReader().setFeature(
                        "http://apache.org/xml/features/disallow-doctype-decl", true);
            } catch (Throwable ignore) {
                // 某些实现的特性名不同，关不掉就算了
            }
            p.parse(in, new Body(sb, r));
        } catch (Stop stop) {
            r.truncated = true;
        } catch (Throwable t) {
            if (sb.length() == 0) r.err = "解析正文失败：" + msgOf(t);
        }
        r.text = tidy(sb.toString());
    }

    /** 收尾清洗：行尾空白、连续空行、连续空格。 */
    static String tidy(String s) {
        String t = s.replace('\r', '\n').replace('\u00a0', ' ');
        t = t.replaceAll("[ \\t]+\\n", "\n");
        t = t.replaceAll("\\n{3,}", "\n\n");
        t = t.replaceAll("[ \\t]{2,}", " ");
        return t.trim();
    }

    private static String msgOf(Throwable t) {
        String m = t.getMessage();
        return (m == null || m.trim().isEmpty()) ? t.getClass().getSimpleName() : m.trim();
    }

    /** 用异常做"读够了"的短路信号，比在 SAX 里层层 return 干净。 */
    private static final class Stop extends RuntimeException {
        Stop() {
            super("enough");
        }
    }

    private static final class Body extends DefaultHandler {
        private final StringBuilder sb;
        private final Result r;
        private boolean inText;
        /** 表格单元格嵌套层数：>0 时段落结束不能换行，否则一行表格会被拆成好几行。 */
        private int tcDepth;

        Body(StringBuilder sb, Result r) {
            this.sb = sb;
            this.r = r;
        }

        private void put(String s) {
            sb.append(s);
            if (sb.length() > MAX_CHARS) throw new Stop();
        }

        /** 去掉行尾的空格和多余的单元格分隔符（空单元格会留下 " | |"）。 */
        private void trimTail() {
            int i = sb.length();
            while (i > 0) {
                char c = sb.charAt(i - 1);
                if (c == ' ' || c == '\t' || c == '|') i--;
                else break;
            }
            sb.setLength(i);
        }

        @Override
        public void startElement(String uri, String local, String qname, Attributes a) {
            String n = name(local, qname);
            if ("t".equals(n)) {
                inText = true;
            } else if ("tc".equals(n)) {
                tcDepth++;
            } else if ("tab".equals(n)) {
                put("\t");
            } else if ("br".equals(n) || "cr".equals(n)) {
                put("\n");
            }
        }

        @Override
        public void characters(char[] ch, int start, int len) {
            if (!inText || len <= 0) return;
            sb.append(ch, start, len);
            if (sb.length() > MAX_CHARS) throw new Stop();
        }

        @Override
        public void endElement(String uri, String local, String qname) {
            String n = name(local, qname);
            if ("t".equals(n)) {
                inText = false;
            } else if ("p".equals(n)) {
                if (tcDepth > 0) {
                    // 单元格里的段落只是行内分段，不能换成换行，否则一行表格被拆散
                    put(" ");
                } else {
                    put("\n");
                    r.paras++;
                }
            } else if ("tc".equals(n)) {
                tcDepth = Math.max(0, tcDepth - 1);
                put(" | ");
            } else if ("tr".equals(n)) {
                trimTail();
                put("\n");
            }
        }

        private static String name(String local, String qname) {
            if (local != null && local.length() > 0) return local;
            if (qname == null) return "";
            int i = qname.indexOf(':');
            return i >= 0 ? qname.substring(i + 1) : qname;
        }
    }
}
