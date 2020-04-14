import logging
import tkinter


class PromptDialog(tkinter.Tk):

  def __init__(self, title, prompt, **kwargs):
    super(PromptDialog, self).__init__()
    self.logger = logging.getLogger('remote_kernel.dialog')
    self.title(title)
    self.geometry("400x120")
    self.frame = tkinter.Frame().pack()
    self.txt = tkinter.StringVar()

    label_kwargs = {k[7:]: kwargs[k] for k in kwargs if k.startswith('label__')}
    entry_kwargs = {k[7:]: kwargs[k] for k in kwargs if k.startswith('entry__')}
    button_kwargs = {k[8:]: kwargs[k] for k in kwargs if k.startswith('button__')}

    self.lblPrompt = tkinter.Label(self.frame, text=prompt, **label_kwargs).pack()
    self.txtPrompt = tkinter.Entry(self.frame, textvariable=self.txt, **entry_kwargs).pack()
    self.btnOK = tkinter.Button(self.frame, text='Ok', command=self.btnOK_click, **button_kwargs).pack()

    self.OK = False

  def btnOK_click(self):
    self.logger.debug('Button OK clicked!')
    self.OK = True
    self.destroy()

  def showDialog(self):
    self.mainloop()
    self.logger.debug('Show dialog returning')
    assert self.OK, 'Dialog cancelled by user'
    return_value = str(self.txt.get())
    del self.txt
    return return_value


class PwdDialog(PromptDialog):

  def __init__(self, title, prompt=None):
    super(PwdDialog, self).__init__(title, prompt, entry__show='*')
